"""'Logo & Drawing to 3D': flat picture (logo, sketch, hand drawing, icon, PNG/JPG/SVG) -> clean printable 3D.

Pipeline: picture -> clean mask(s) (threshold with auto Otsu or a colour count, despeckle, smoothing)
-> true vector outlines with holes kept (shapely) -> sized by target width in mm -> one of four outputs:
  extrude       shape height + optional base plate (none/rect/rounded/outline) + optional keyring hole
  cutter        cookie cutter: thin wall along the outline + wider flange that lies on the bed
  stamp         raised (optionally mirrored, for ink) or recessed into a base
  layers        2-4 colour layers (k-means) stacked at different heights, one body per colour (3MF objects)
SVG files are read as vectors directly (paths, polygons, rects, circles, ellipses; basic transforms).
Every output is checked watertight; lines thinner than the nozzle are flagged and can be auto-thickened.
Coordinates: X right, Y up, Z height (bed at Z=0), millimetres.
"""
from __future__ import annotations

import io
import math
import re

import numpy as np
import trimesh
from PIL import Image, ImageDraw
from shapely import affinity
from shapely.geometry import MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union
from skimage import filters, measure, morphology

from .geometry import Body, Model

MODES = ("extrude", "cutter", "stamp", "layers")
BASES = ("none", "rect", "rounded", "outline")
WORK_PX = 700                     # long side used for tracing (enough for crisp logos, quick to compute)
MAX_SVG_BYTES = 2_000_000
DEFAULTS = dict(
    out="extrude", width_mm=80.0, threshold=-1, invert=False, color_mode=False, colors=2,
    despeckle=30, smooth=1.0, height_mm=3.0, base="none", base_mm=2.0, base_margin_mm=3.0,
    keyring=False, hole_mm=4.0, wall_mm=1.0, cutter_mm=14.0, flange_mm=5.0, flange_thick_mm=2.0,
    stamp_style="raised", relief_mm=1.5, mirror=True, layers=3, layer_mm=1.0,
    min_feature_mm=0.8, thicken=False)
LIMITS = dict(width_mm=(5, 400), height_mm=(0.4, 50), base_mm=(0.4, 20), base_margin_mm=(0, 30), hole_mm=(2, 12),
              wall_mm=(0.6, 3.0), cutter_mm=(5, 40), flange_mm=(0, 15), flange_thick_mm=(0.6, 6), relief_mm=(0.4, 10),
              layer_mm=(0.2, 6), min_feature_mm=(0.2, 3), despeckle=(0, 5000), smooth=(0, 5), colors=(2, 6), layers=(2, 4),
              threshold=(-1, 255))
FRIENDLY = {"width_mm": "Width", "height_mm": "Shape height", "base_mm": "Base thickness", "wall_mm": "Cutter wall",
            "cutter_mm": "Cutter height", "relief_mm": "Stamp depth", "layer_mm": "Layer step", "layers": "Colour layers"}


class TraceError(ValueError):
    """Message is safe to show to the person as-is."""


def clean_params(p: dict | None) -> dict:
    out = dict(DEFAULTS)
    for k, v in (p or {}).items():
        if k not in DEFAULTS:
            continue
        d = DEFAULTS[k]
        try:
            if isinstance(d, bool):
                v = v if isinstance(v, bool) else str(v).lower() in ("1", "true", "on", "yes")
            elif isinstance(d, int) and not isinstance(d, bool):
                v = int(float(v))
            elif isinstance(d, float):
                v = float(v)
            else:
                v = str(v)
        except (TypeError, ValueError):
            raise TraceError(f"{FRIENDLY.get(k, k)} needs a number.")
        if isinstance(v, float) and not math.isfinite(v):
            raise TraceError(f"{FRIENDLY.get(k, k)} needs a number.")
        if k in LIMITS:
            lo, hi = LIMITS[k]
            v = type(v)(min(max(v, lo), hi))
        out[k] = v
    if out["out"] not in MODES:
        raise TraceError("Pick one of: Extrude, Cookie cutter, Stamp, Colour layers.")
    if out["base"] not in BASES:
        out["base"] = "none"
    if out["stamp_style"] not in ("raised", "recessed"):
        out["stamp_style"] = "raised"
    return out


# ------------------------------------------------------------------ raster -> masks
def _work(im: Image.Image) -> np.ndarray:
    im = im.convert("RGB")
    k = WORK_PX / max(im.size)
    if k < 1:
        im = im.resize((max(2, round(im.width * k)), max(2, round(im.height * k))), Image.LANCZOS)
    return np.asarray(im, dtype=np.float64) / 255.0


def kmeans(px: np.ndarray, k: int, iters: int = 20) -> tuple[np.ndarray, np.ndarray]:
    """Plain deterministic k-means on RGB rows (initialised on brightness quantiles). -> (labels, centres)."""
    luma = px @ np.array([0.299, 0.587, 0.114])
    order = np.argsort(luma)
    cent = np.stack([px[order[int((i + 0.5) / k * (len(px) - 1))]] for i in range(k)])
    sample = px[:: max(1, len(px) // 60000)]
    for _ in range(iters):
        lab = np.argmin(((sample[:, None, :] - cent[None]) ** 2).sum(-1), 1)
        new = np.stack([sample[lab == i].mean(0) if np.any(lab == i) else cent[i] for i in range(k)])
        if np.allclose(new, cent, atol=1e-4):
            break
        cent = new
    labels = np.empty(len(px), np.int32)
    for s in range(0, len(px), 200000):
        labels[s:s + 200000] = np.argmin(((px[s:s + 200000, None, :] - cent[None]) ** 2).sum(-1), 1)
    return labels, cent


def _despeckle(mask: np.ndarray, area: int) -> np.ndarray:
    if area > 0:
        mask = morphology.remove_small_objects(mask, max_size=area) if _new_skimage() else morphology.remove_small_objects(mask, area)
        mask = ~(morphology.remove_small_objects(~mask, max_size=area) if _new_skimage() else morphology.remove_small_objects(~mask, area))
    return mask


def _new_skimage() -> bool:
    import inspect
    return "max_size" in inspect.signature(morphology.remove_small_objects).parameters


def _background_label(lab2d: np.ndarray) -> int:
    edge = np.concatenate([lab2d[0], lab2d[-1], lab2d[:, 0], lab2d[:, -1]])
    return int(np.bincount(edge).argmax())


def masks_from_image(im: Image.Image, p: dict) -> dict:
    """-> {'ink': bool mask, 'layers': [(mask, '#rrggbb'), ...] (layers mode), 'bg': '#rrggbb', 'threshold': used}."""
    rgb = _work(im)
    h, w, _ = rgb.shape
    if p["smooth"] > 0:
        rgb = filters.gaussian(rgb, sigma=p["smooth"], channel_axis=-1)
    out = {"bg": "#FFFFFF", "layers": [], "threshold": None}
    if p["out"] == "layers" or p["color_mode"]:
        k = p["layers"] + 1 if p["out"] == "layers" else p["colors"]
        labels, cent = kmeans(rgb.reshape(-1, 3), k)
        lab2d = labels.reshape(h, w)
        bg = _background_label(lab2d)
        out["bg"] = _hex(cent[bg])
        ink = lab2d != bg
        if p["invert"]:
            ink = ~ink
        ink = _despeckle(ink, p["despeckle"])
        out["ink"] = ink
        if p["out"] == "layers":
            idx = [i for i in range(k) if i != bg]
            idx.sort(key=lambda i: -(lab2d == i).sum())          # biggest colour lowest, small details on top
            for i in idx:
                m = _despeckle((lab2d == i) & ink, p["despeckle"])
                if m.sum() > 0:
                    out["layers"].append((m, _hex(cent[i])))
        return out
    g = rgb @ np.array([0.299, 0.587, 0.114])
    t = p["threshold"] / 255.0 if p["threshold"] >= 0 else float(filters.threshold_otsu(g)) if g.max() - g.min() > 1e-3 else 0.5
    out["threshold"] = round(t * 255)
    ink = g < t
    if ink[[0, 0, -1, -1], [0, -1, 0, -1]].sum() >= 3:        # light drawing on a dark background: the ink is the light part
        ink = ~ink
    if p["invert"]:
        ink = ~ink
    out["ink"] = _despeckle(ink, p["despeckle"])
    return out


def _hex(c) -> str:
    c = np.clip(np.asarray(c) * 255, 0, 255).round().astype(int)
    return "#%02X%02X%02X" % tuple(c[:3])


def mask_to_geom(mask: np.ndarray, simplify_px: float = 0.6):
    """Binary mask -> shapely (Multi)Polygon in pixel units, Y up, with holes kept (even-odd nesting of the contours)."""
    pad = np.pad(mask.astype(float), 1)
    rings = []
    for c in measure.find_contours(pad, 0.5):
        if len(c) < 4:
            continue
        xy = np.column_stack([c[:, 1] - 1, (mask.shape[0] - 1) - (c[:, 0] - 1)])
        poly = Polygon(xy).buffer(0)
        if poly.area > 0.5:
            rings.append(poly)
    geom = Polygon()
    for r in sorted(rings, key=lambda r: -r.area):
        geom = geom.symmetric_difference(r)              # contours of a mask never cross: even-odd gives islands and holes
    if simplify_px > 0:
        geom = geom.simplify(simplify_px, preserve_topology=True)
    return _polys(geom.buffer(0))


def _polys(g):
    if g.is_empty:
        return MultiPolygon()
    if isinstance(g, Polygon):
        return MultiPolygon([g])
    if isinstance(g, MultiPolygon):
        return g
    return MultiPolygon([x for x in getattr(g, "geoms", []) if isinstance(x, Polygon) and x.area > 0])


# ------------------------------------------------------------------ SVG -> vectors
_NUM = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
_CMD = re.compile(r"([MmLlHhVvCcSsQqTtAaZz])|([-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?)")


def is_svg(data: bytes) -> bool:
    head = data[:2048].lstrip().lower()
    return head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in data[:4096].lower())


def _parse_transform(s: str) -> np.ndarray:
    m = np.eye(3)
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", s or ""):
        a = [float(x) for x in _NUM.findall(args)]
        t = np.eye(3)
        if name == "matrix" and len(a) == 6:
            t = np.array([[a[0], a[2], a[4]], [a[1], a[3], a[5]], [0, 0, 1]])
        elif name == "translate" and a:
            t[0, 2] = a[0]; t[1, 2] = a[1] if len(a) > 1 else 0
        elif name == "scale" and a:
            t[0, 0] = a[0]; t[1, 1] = a[1] if len(a) > 1 else a[0]
        elif name == "rotate" and a:
            r = math.radians(a[0]); c, s_ = math.cos(r), math.sin(r)
            rot = np.array([[c, -s_, 0], [s_, c, 0], [0, 0, 1]])
            if len(a) == 3:
                tr = np.array([[1, 0, a[1]], [0, 1, a[2]], [0, 0, 1]]); rot = tr @ rot @ np.linalg.inv(tr)
            t = rot
        m = m @ t
    return m


def _path_subpaths(d: str, steps: int = 16) -> list[np.ndarray]:
    toks = [(c, float(n) if n else None) for c, n in _CMD.findall(d)]
    subs, cur, pos, start, last_ctrl, cmd, i = [], [], np.zeros(2), np.zeros(2), None, None, 0

    def nums(k):
        nonlocal i
        vals = []
        while len(vals) < k:
            if i >= len(toks) or toks[i][0]:
                raise TraceError("This SVG has a path we can't read. Try exporting it again, or use a PNG.")
            vals.append(toks[i][1]); i += 1
        return vals

    def bez(pts):
        t = np.linspace(0, 1, steps + 1)[1:, None]
        if len(pts) == 3:
            return (1 - t) ** 2 * pts[0] + 2 * (1 - t) * t * pts[1] + t ** 2 * pts[2]
        return (1 - t) ** 3 * pts[0] + 3 * (1 - t) ** 2 * t * pts[1] + 3 * (1 - t) * t ** 2 * pts[2] + t ** 3 * pts[3]

    while i < len(toks):
        if toks[i][0]:
            cmd = toks[i][0]; i += 1
            if cmd in "Zz":
                if cur:
                    subs.append(np.array(cur)); cur = []
                pos = start.copy(); last_ctrl = None
                continue
        elif cmd is None:
            raise TraceError("This SVG has a path we can't read. Try exporting it again, or use a PNG.")
        rel = cmd.islower(); C = cmd.upper(); base = pos if rel else np.zeros(2)
        if C == "M":
            if cur:
                subs.append(np.array(cur))
            pos = base + nums(2); start = pos.copy(); cur = [pos.copy()]
            cmd = "l" if rel else "L"; last_ctrl = None
        elif C == "L":
            pos = base + nums(2); cur.append(pos.copy()); last_ctrl = None
        elif C == "H":
            x = nums(1)[0]; pos = np.array([pos[0] + x if rel else x, pos[1]]); cur.append(pos.copy()); last_ctrl = None
        elif C == "V":
            y = nums(1)[0]; pos = np.array([pos[0], pos[1] + y if rel else y]); cur.append(pos.copy()); last_ctrl = None
        elif C in "CS":
            if C == "C":
                a = nums(6); c1, c2, e = base + a[0:2], base + a[2:4], base + a[4:6]
            else:
                a = nums(4); c1 = 2 * pos - last_ctrl if last_ctrl is not None else pos.copy(); c2, e = base + a[0:2], base + a[2:4]
            cur.extend(bez([pos, c1, c2, e])); last_ctrl = c2; pos = e
        elif C in "QT":
            if C == "Q":
                a = nums(4); c1, e = base + a[0:2], base + a[2:4]
            else:
                a = nums(2); c1 = 2 * pos - last_ctrl if last_ctrl is not None else pos.copy(); e = base + a
            cur.extend(bez([pos, c1, e])); last_ctrl = c1; pos = e
        elif C == "A":                               # elliptical arc: approximated by its chord points (good enough for icons)
            a = nums(7); e = base + a[5:7]
            cur.extend(np.linspace(pos, e, steps + 1)[1:]); pos = e; last_ctrl = None
        if not cur:
            cur = [pos.copy()]
    if cur:
        subs.append(np.array(cur))
    return [s for s in subs if len(s) >= 3]


def svg_to_geom(data: bytes):
    """SVG bytes -> shapely MultiPolygon in SVG user units, Y up. Uses the vectors directly; refuses anything unsafe or empty."""
    from lxml import etree
    if len(data) > MAX_SVG_BYTES:
        raise TraceError("That SVG is very large. Try a simpler one, or a PNG.")
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False, remove_comments=True)
    try:
        root = etree.fromstring(data, parser)
    except Exception:
        raise TraceError("We couldn't open that SVG. Try saving it again, or use a PNG.")
    if root is None or not str(root.tag).endswith("svg"):
        raise TraceError("We couldn't open that SVG. Try saving it again, or use a PNG.")
    if root.find(".//{*}image") is not None:
        raise TraceError("This SVG has a picture inside it. Use the picture itself (PNG or JPG) instead.")
    shapes = []

    def walk(el, m):
        tag = str(el.tag).split("}")[-1]
        if tag in ("defs", "clipPath", "mask", "symbol", "style", "title", "desc", "metadata", "text"):
            return
        if (el.get("display") == "none") or ("display:none" in (el.get("style") or "").replace(" ", "")):
            return
        m = m @ _parse_transform(el.get("transform"))
        f = lambda k, d=0.0: float((_NUM.findall(el.get(k) or "") or [d])[0])
        rings = []
        if tag == "path":
            rings = _path_subpaths(el.get("d") or "")
        elif tag in ("polygon", "polyline"):
            n = [float(x) for x in _NUM.findall(el.get("points") or "")]
            if len(n) >= 6:
                rings = [np.array(n[: len(n) // 2 * 2]).reshape(-1, 2)]
        elif tag == "rect":
            x, y, w, h = f("x"), f("y"), f("width"), f("height")
            if w > 0 and h > 0:
                rings = [np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]])]
        elif tag in ("circle", "ellipse"):
            cx, cy = f("cx"), f("cy")
            rx = f("r") if tag == "circle" else f("rx"); ry = f("r") if tag == "circle" else f("ry")
            if rx > 0 and ry > 0:
                a = np.linspace(0, 2 * np.pi, 64, endpoint=False)
                rings = [np.column_stack([cx + rx * np.cos(a), cy + ry * np.sin(a)])]
        if rings:
            fill = (el.get("fill") or "").strip().lower()
            st = (el.get("style") or "").replace(" ", "").lower()
            if fill == "none" or "fill:none" in st:
                sw = f("stroke-width", 1.0)
                g = unary_union([Polygon(r).exterior.buffer(sw / 2) for r in rings if len(r) >= 3])
            else:
                g = Polygon()
                for r in rings:
                    p = Polygon(r).buffer(0)
                    g = g.symmetric_difference(p)           # even-odd: the counters of letters stay open
            if not g.is_empty:
                shapes.append(affinity.affine_transform(g, [m[0, 0], m[0, 1], m[1, 0], m[1, 1], m[0, 2], m[1, 2]]))
        for ch in el:
            if isinstance(ch.tag, str):
                walk(ch, m)

    walk(root, np.eye(3))
    if len(shapes) > 20000:
        raise TraceError("That SVG has too many pieces. Try a simpler one.")
    g = unary_union(shapes) if shapes else Polygon()
    if g.is_empty or g.area <= 0:
        raise TraceError("We couldn't find any filled shapes in that SVG. Try a PNG instead.")
    g = affinity.scale(g, 1, -1, origin=(0, 0))       # SVG Y points down
    return _polys(g.buffer(0))


# ------------------------------------------------------------------ geometry helpers
def _fit_width(g, width_mm: float, ref=None):
    """Scale + move so the shape (or ref) is width_mm wide, proportions kept, lower-left at 0,0."""
    ref = ref if ref is not None else g
    minx, miny, maxx, maxy = ref.bounds
    k = width_mm / max(maxx - minx, 1e-9)
    return affinity.translate(affinity.scale(g, k, k, origin=(0, 0)), -minx * k, -miny * k), k


def _extrude(g, z0: float, z1: float) -> trimesh.Trimesh | None:
    parts = [trimesh.creation.extrude_polygon(p, z1 - z0) for p in _polys(g).geoms if p.area > 1e-6]
    if not parts:
        return None
    m = trimesh.util.concatenate(parts)
    m.apply_translation([0, 0, z0])
    return m


def _bool(op: str, meshes):
    meshes = [m for m in meshes if m is not None and len(m.faces)]
    if len(meshes) == 1:
        return meshes[0]
    return getattr(trimesh.boolean, op)(meshes, engine="manifold")


def thin_parts(g, min_mm: float):
    """Pieces of the shape narrower than min_mm (an opening with radius min/2 removes them)."""
    r = min_mm / 2
    opened = g.buffer(-r, join_style="round").buffer(r, join_style="round")
    rest = _polys(g.difference(opened).buffer(-r * 0.05))
    big = [p for p in rest.geoms if p.area > 1.5 * r * r]   # ignore the tiny slivers every sharp corner leaves
    return _polys(unary_union(big)) if big else MultiPolygon()


def thicken(g, min_mm: float):
    thin = thin_parts(g, min_mm)
    if thin.is_empty:
        return g
    return _polys(unary_union([g, thin.buffer(min_mm / 2, join_style="round")]).buffer(0))


def _keyring(target, hole_mm: float):
    """-> (tab disc, hole disc) sitting on the top edge of target."""
    minx, miny, maxx, maxy = target.bounds
    cx = (minx + maxx) / 2
    top = [c for p in _polys(target).geoms for c in p.exterior.coords if c[1] > maxy - 1e-6]
    if top:
        cx = min(top, key=lambda c: abs(c[0] - cx))[0]
    r = hole_mm / 2; ring = 2.5
    c = Point(cx, maxy + r + 0.5)
    return c.buffer(r + ring, 48), c.buffer(r, 48)


def _flat_base(g, kind: str, margin: float):
    minx, miny, maxx, maxy = g.bounds
    if kind == "rect":
        return box(minx - margin, miny - margin, maxx + margin, maxy + margin)
    if kind == "rounded":
        rad = max(0.5, min(margin, 6.0, (maxx - minx) / 4, (maxy - miny) / 4))
        return box(minx - margin + rad, miny - margin + rad, maxx + margin - rad, maxy + margin - rad).buffer(rad, 32)
    if kind == "outline":
        return unary_union([Polygon(p.exterior) for p in _polys(g.buffer(max(margin, 0.5), join_style="round")).geoms])
    return None


# ------------------------------------------------------------------ build
def source_geoms(data: bytes, im: Image.Image | None, p: dict) -> dict:
    """-> {'ink': MultiPolygon (px or svg units), 'layers': [(geom, colour)], 'bg': colour, 'svg': bool, 'threshold'}."""
    if is_svg(data):
        if p["out"] == "layers":
            raise TraceError("Colour layers need a PNG or JPG picture. For an SVG, pick Extrude, Cookie cutter or Stamp.")
        return {"ink": svg_to_geom(data), "layers": [], "bg": "#FFFFFF", "svg": True, "threshold": None}
    if im is None:
        from .geometry import load_image
        im = load_image(data)
    m = masks_from_image(im, p)
    simp = 0.4 + 0.3 * p["smooth"]
    ink = mask_to_geom(m["ink"], simp)
    layers = [(mask_to_geom(mk, simp), col) for mk, col in m["layers"]]
    return {"ink": ink, "layers": [(g, c) for g, c in layers if not g.is_empty], "bg": m["bg"], "svg": False,
            "threshold": m["threshold"]}


def trace(data: bytes, im: Image.Image | None, params: dict) -> dict:
    """Vectors in millimetres (+ warnings) without making any 3D: used by the live 2D preview and by build()."""
    p = clean_params(params)
    src = source_geoms(data, im, p)
    ink = src["ink"]
    if ink.is_empty or ink.area <= 0:
        raise TraceError("We couldn't find a shape in that picture. Try moving the Threshold slider, or tick Swap shape and background.")
    ink_mm, k = _fit_width(ink, p["width_mm"])
    layers_mm = [(_fit_width(g, p["width_mm"], ref=ink)[0], c) for g, c in src["layers"]]
    if p["out"] == "stamp" and p["stamp_style"] == "raised" and p["mirror"]:
        mx = p["width_mm"] / 2
        ink_mm = affinity.scale(ink_mm, -1, 1, origin=(mx, 0))
    min_area = max(0.0, p["despeckle"]) * k * k
    ink_mm = _polys(MultiPolygon([q for q in ink_mm.geoms if q.area >= min_area * 0.5]) if min_area else ink_mm)
    warnings, notes = [], []
    thin_before = MultiPolygon()
    if p["out"] != "cutter":
        thin_before = thin_parts(ink_mm, p["min_feature_mm"])
        if not thin_before.is_empty:
            if p["thicken"]:
                ink_mm = thicken(ink_mm, p["min_feature_mm"])
                layers_mm = [(thicken(g, p["min_feature_mm"]), c) for g, c in layers_mm]
                notes.append(f"Thin lines were made thicker so they are at least {p['min_feature_mm']:g} mm wide.")
            else:
                warnings.append(f"Some lines are thinner than {p['min_feature_mm']:g} mm, so they may not print. "
                                "Tick Make thin lines thicker, or make the model wider.")
    holes = sum(len(q.interiors) for q in ink_mm.geoms)
    return {"p": p, "ink": ink_mm, "layers": layers_mm, "bg": src["bg"], "svg": src["svg"], "threshold": src["threshold"],
            "holes": holes, "pieces": len(ink_mm.geoms), "thin": thin_before, "warnings": warnings, "notes": notes}


def build(data: bytes, im: Image.Image | None, params: dict) -> Model:
    t = trace(data, im, params)
    p, ink = t["p"], t["ink"]
    bodies: list[tuple[str, trimesh.Trimesh, str]] = []
    info = {"trace": {"out": p["out"], "holes": t["holes"], "pieces": t["pieces"], "threshold": t["threshold"],
                      "from_svg": t["svg"]}, "warnings": list(t["warnings"]), "notes": list(t["notes"])}
    hole = None

    if p["out"] == "extrude":
        base = _flat_base(ink, p["base"], p["base_margin_mm"]) if p["base"] != "none" else None
        z = p["base_mm"] if base is not None else 0.0
        if p["keyring"]:
            tab, hole = _keyring(base if base is not None else ink, p["hole_mm"])
            if base is not None:
                base = base.union(tab).difference(hole)
            else:
                ink = _polys(ink.union(tab.difference(hole)))
            ink = _polys(ink.difference(hole))
        if base is not None:
            bodies.append(("Base", _extrude(base, 0, z), "#FFFFFF"))
        bodies.append(("Shape", _extrude(ink, z, z + p["height_mm"]), "#E4572E"))

    elif p["out"] == "cutter":
        outline = _polys(unary_union([Polygon(q.exterior) for q in ink.geoms]).buffer(0))
        outline = _polys(outline.buffer(0.3, join_style="round").buffer(-0.3, join_style="round"))   # tiny notches the wall can't follow
        w = p["wall_mm"]
        wall = outline.buffer(w, join_style="round").difference(outline)
        meshes = [_extrude(wall, 0, p["cutter_mm"])]
        if p["flange_mm"] > 0:
            flange = outline.buffer(w + p["flange_mm"], join_style="round").difference(outline)
            meshes.append(_extrude(flange, 0, p["flange_thick_mm"]))
        bodies.append(("Cookie cutter", _bool("union", meshes), "#4A90D9"))
        info["wall_mm"] = w
        info["notes"].append("Print it flange-down. The thin edge at the top does the cutting; push on the wide flange.")

    elif p["out"] == "stamp":
        margin = max(p["base_margin_mm"], 2.0)
        base = _flat_base(ink, "rounded", margin)
        T = p["base_mm"] if p["stamp_style"] == "raised" else max(p["base_mm"], p["relief_mm"] + 1.0)
        if p["stamp_style"] == "raised":
            bodies.append(("Stamp base", _extrude(base, 0, T), "#FFFFFF"))
            bodies.append(("Stamp face", _extrude(ink, T, T + p["relief_mm"]), "#E4572E"))
        else:
            cut = _extrude(ink.buffer(0), T - p["relief_mm"], T + 1)
            bodies.append(("Embossed plate", _bool("difference", [_extrude(base, 0, T), cut]), "#FFFFFF"))
        if p["stamp_style"] == "raised" and p["mirror"]:
            info["notes"].append("The design is mirrored, so it reads the right way when you stamp it.")

    else:  # layers
        layers = t["layers"]
        if not layers:
            raise TraceError("We couldn't find separate colours in that picture. Try fewer colour layers.")
        outline = _polys(unary_union([g for g, _ in layers]))
        base = _flat_base(outline, p["base"] if p["base"] != "none" else "outline", max(p["base_margin_mm"], 1.0))
        bodies.append(("Base", _extrude(base, 0, p["base_mm"]), t["bg"]))
        claimed = MultiPolygon()
        regions = []
        for g, col in reversed(layers):                    # top colour keeps its full area; lower ones give way
            reg = _polys(g.difference(claimed).buffer(-0.01).buffer(0.01))
            claimed = _polys(unary_union([claimed, g]))
            regions.append((reg, col))
        regions.reverse()
        changes = []
        for n, (reg, col) in enumerate(regions, 1):
            top = p["base_mm"] + n * p["layer_mm"]
            mesh = _extrude(reg, p["base_mm"], top)
            if mesh is not None:
                bodies.append((f"Colour {n} {col}", mesh, col))
                changes.append({"colour": col, "from_mm": round(p["base_mm"] + (n - 1) * p["layer_mm"], 2), "to_mm": round(top, 2)})
        info["colours"] = [t["bg"]] + [c["colour"] for c in changes]
        info["colour_changes"] = changes
        info["notes"].append("The 3MF file has one object per colour, so you can give each its own filament (AMS / CFS). "
                             "For a single-nozzle printer, change filament at the heights listed.")

    bodies = [(n, m, c) for n, m, c in bodies if m is not None and len(m.faces)]
    if not bodies:
        raise TraceError("That made an empty model. Try a different Threshold or a wider size.")
    model = Model(mode="trace2d")
    for n, m, c in bodies:
        model.bodies.append(Body(n, np.asarray(m.vertices, np.float64), np.asarray(m.faces, np.int64), c))
    one = _bool("union", [m for _, m, _ in bodies]) if len(bodies) > 1 else bodies[0][1]
    model.single = (np.asarray(one.vertices, np.float64), np.asarray(one.faces, np.int64))
    info["watertight"] = bool(one.is_watertight and one.volume > 0)
    ext = one.extents
    info["size_mm"] = [round(float(x), 1) for x in ext]
    model.info = info
    model.thumb = thumbnail(bodies)
    return model


def thumbnail(bodies, px: int = 256) -> np.ndarray:
    """Top-down picture of the bodies, lowest first (for history cards)."""
    allv = np.vstack([m.vertices for _, m, _ in bodies])
    lo, hi = allv.min(0), allv.max(0)
    k = (px - 16) / max(hi[0] - lo[0], hi[1] - lo[1], 1e-6)
    img = Image.new("RGB", (px, px), (245, 245, 245))
    d = ImageDraw.Draw(img)
    for _, m, c in sorted(bodies, key=lambda b: b[1].bounds[1][2]):
        rgb = tuple(int(c.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)) if c else (200, 200, 200)
        if rgb == (255, 255, 255):
            rgb = (215, 215, 215)
        top = m.vertices[:, 2] > m.bounds[1][2] - 1e-6
        for f in m.faces:
            if top[f].all():
                pts = [(8 + (m.vertices[i][0] - lo[0]) * k, px - 8 - (m.vertices[i][1] - lo[1]) * k) for i in f]
                d.polygon(pts, fill=rgb)
    return np.asarray(img)


def preview_svg(t: dict) -> str:
    """Small SVG of the traced outlines (holes stay holes: even-odd fill), thin bits in red."""
    g = t["ink"]
    geoms = [(gg, c) for gg, c in t["layers"]] if t["p"]["out"] == "layers" and t["layers"] else [(g, "#222")]
    minx, miny, maxx, maxy = g.bounds if not g.is_empty else (0, 0, 1, 1)
    pad = max(maxx - minx, maxy - miny) * 0.04 + 0.5
    W, H = maxx - minx + 2 * pad, maxy - miny + 2 * pad

    def path(geom):
        s = []
        for q in _polys(geom).geoms:
            for ring in [q.exterior, *q.interiors]:
                s.append("M" + " L".join(f"{x - minx + pad:.2f},{maxy - y + pad:.2f}" for x, y in ring.coords) + "Z")
        return "".join(s)

    body = "".join(f'<path d="{path(gg)}" fill="{c}" fill-rule="evenodd"/>' for gg, c in geoms)
    if not t["thin"].is_empty and not t["p"]["thicken"]:
        body += f'<path d="{path(t["thin"])}" fill="#D7263D" fill-rule="evenodd"/>'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.2f} {H:.2f}" role="img" '
            f'aria-label="Traced outline, {t["pieces"]} pieces, {t["holes"]} holes">{body}</svg>')
