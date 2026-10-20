"""TorchC0 (ZEIM's resin program): resin print settings, auto-orient (tilt), hollow + drain holes, simple tree-free
pillar supports with a raft, print estimates, and STL/3MF export for any resin slicer (CHITUBOX, Lychee, Photon
Workshop, VoxelDance Tango, PrusaSlicer SLA, PreForm). Pure ZEIM code (trimesh / numpy / manifold3d); no GPL code.

TorchC0 does not write native layer files (.ctb/.pwmx/.goo): those formats are vendor-specific and the public
encoders we know of are GPL/AGPL, so the export is a supported, oriented mesh that the printer's own slicer
turns into layers with the exposure numbers shown here."""
from __future__ import annotations

import math

import numpy as np
import trimesh

from app.core import meshedit

NAME = "TorchC0"

# Starting values for a standard (non-ABS-like) resin on a monochrome-LCD MSLA printer. These match the typical
# ranges resin and printer makers publish (layer 0.03-0.05 mm, normal exposure ~1.5-3 s, bottom ~20-35 s over 4-6
# layers, lift 5-8 mm). Every resin differs: the UI says to run an exposure test (e.g. a validation matrix) first.
PRESETS = {
    "detail":   {"label": "Fine detail", "help": "Minis and jewellery: thin 0.03 mm layers, slow.",
                 "layer_mm": 0.03, "exposure_s": 2.0, "bottom_exposure_s": 25.0, "bottom_layers": 5,
                 "lift_mm": 6.0, "lift_speed_mm_min": 60.0},
    "standard": {"label": "Standard", "help": "Most prints: 0.05 mm layers.",
                 "layer_mm": 0.05, "exposure_s": 2.5, "bottom_exposure_s": 30.0, "bottom_layers": 5,
                 "lift_mm": 6.0, "lift_speed_mm_min": 65.0},
    "fast":     {"label": "Fast draft", "help": "Quick checks: 0.08 mm layers, less detail.",
                 "layer_mm": 0.08, "exposure_s": 3.2, "bottom_exposure_s": 30.0, "bottom_layers": 4,
                 "lift_mm": 6.0, "lift_speed_mm_min": 80.0},
}
DEFAULT_PRESET = "standard"
LIMITS = {"layer_mm": (0.01, 0.2), "exposure_s": (0.5, 30.0), "bottom_exposure_s": (5.0, 120.0), "bottom_layers": (1, 15),
          "lift_mm": (1.0, 15.0), "lift_speed_mm_min": (10.0, 300.0), "tilt_deg": (0.0, 60.0), "wall_mm": (0.0, 6.0),
          "drain_mm": (0.0, 10.0), "price": (0.0, 10000.0), "support_spacing_mm": (1.5, 10.0), "base_lift_mm": (0.0, 15.0)}
SAFETY = ["Wear nitrile gloves and eye protection; uncured resin irritates skin and eyes.",
          "Print and wash in a ventilated room; keep resin away from children, pets and food areas.",
          "Wash prints in IPA (or the resin maker's wash), then cure under UV. Cure used IPA and resin waste in sunlight before disposal; never pour it down a drain.",
          "Hollow prints need drain holes, or trapped liquid resin can crack the print later."]
# Typical standard-resin street price (~30 per litre in USD/EUR, 2026) and density (~1.1 g/ml, standard resins 1.05-1.25).
DEFAULT_PRICE = 30.0
DEFAULT_PRICE_UNIT = "l"
RESIN_DENSITY_G_ML = 1.1
TEST_NOTE = "Starting values only. Run an exposure test with your resin (most resin makers publish one) and adjust in your slicer."


class ResinError(ValueError):
    """Bad TorchC0 input; message is safe to show."""


def _num(o, key, default, cast=float):
    v = o.get(key, default)
    if v in (None, ""):
        v = default
    try:
        x = cast(v)
    except (TypeError, ValueError):
        raise ResinError(f"{key.replace('_', ' ')} must be a number.") from None
    lo, hi = LIMITS[key]
    if not (lo <= x <= hi) or (isinstance(x, float) and not math.isfinite(x)):
        raise ResinError(f"{key.replace('_', ' ')} must be between {lo:g} and {hi:g}.")
    return x


def settings(opts: dict | None = None) -> dict:
    """Preset first, then explicit values. Defaults: 30° tilt, 2 mm hollow wall, 3 mm drain + vent holes, supports on."""
    o = dict(opts or {})
    preset = o.get("preset") or DEFAULT_PRESET
    if preset not in PRESETS:
        raise ResinError("Unknown TorchC0 preset.")
    pr = PRESETS[preset]
    s = {"preset": preset}
    for k in ("layer_mm", "exposure_s", "bottom_exposure_s", "lift_mm", "lift_speed_mm_min"):
        s[k] = _num(o, k, pr[k])
    s["bottom_layers"] = _num(o, "bottom_layers", pr["bottom_layers"], int)
    s["tilt_deg"] = _num(o, "tilt_deg", 30.0)
    s["wall_mm"] = _num(o, "wall_mm", 2.0)
    s["drain_mm"] = _num(o, "drain_mm", 3.0)
    s["support_spacing_mm"] = _num(o, "support_spacing_mm", 4.0)
    s["base_lift_mm"] = _num(o, "base_lift_mm", 5.0)
    s["price"] = _num(o, "price", DEFAULT_PRICE)
    s["price_unit"] = o.get("price_unit") or DEFAULT_PRICE_UNIT
    if s["price_unit"] not in ("l", "kg"):
        raise ResinError("Price unit must be per litre (l) or per kg.")
    s["hollow"] = str(o.get("hollow", "true")).lower() in ("1", "true", "on", "yes")
    s["supports"] = str(o.get("supports", "true")).lower() in ("1", "true", "on", "yes")
    if s["hollow"] and 0 < s["wall_mm"] < 1.0:
        raise ResinError("Hollow walls under 1 mm crack easily in resin. Use 1 mm or more, or turn hollowing off.")
    return s


def orient(m: trimesh.Trimesh, tilt_deg: float) -> trimesh.Trimesh:
    """Tilt about X so no big flat area meets the screen in one layer (smaller peel force, fewer suction cups),
    then sit the lowest point on z=0."""
    m = m.copy()
    if tilt_deg:
        m.apply_transform(trimesh.transformations.rotation_matrix(math.radians(tilt_deg), [1, 0, 0], m.centroid))
    m.apply_translation(-m.bounds[0] * [0, 0, 1])
    return m


def support_points(m: trimesh.Trimesh, spacing: float, max_angle_deg: float = 45.0, envelope=None) -> np.ndarray:
    """Points on downward-facing surfaces (steeper than max_angle_deg from vertical-down counts as overhang),
    thinned to one per `spacing` mm cell, plus every local lowest vertex (islands that would start mid-air).
    `envelope` (the solid before hollowing, same placement): a point whose outward side lies inside it is the inner
    ceiling of a cavity or a hole wall, which resin prints don't support, so it is left out."""
    down = m.face_normals[:, 2] < -math.cos(math.radians(max_angle_deg))
    pts, nrm = [], []
    if down.any():
        area = m.area_faces[down].sum()
        n = int(min(20000, max(50, area / (spacing * spacing) * 4)))
        idx = np.nonzero(down)[0]
        sub = m.submesh([idx], append=True)
        if len(sub.faces):
            p, fi = trimesh.sample.sample_surface_even(sub, n, radius=spacing * 0.5, seed=3)
            pts.append(p); nrm.append(sub.face_normals[fi])
    v = m.vertices; nb = m.vertex_neighbors
    mins = [i for i in range(len(v)) if nb[i] and all(v[i, 2] < v[j, 2] - 1e-9 for j in nb[i])]
    if mins:
        pts.append(v[mins]); nrm.append(np.tile([0, 0, -1.0], (len(mins), 1)))
    if not pts:
        return np.zeros((0, 3))
    p, nn = np.vstack(pts), np.vstack(nrm)
    if envelope is not None and len(p):
        inner = envelope.contains(p + nn * 0.3)
        p = p[~inner]
    if not len(p):
        return np.zeros((0, 3))
    keys = np.floor(p[:, :2] / spacing).astype(np.int64)
    order = np.lexsort((p[:, 2], keys[:, 1], keys[:, 0]))        # lowest point per cell wins
    _, first = np.unique(keys[order], axis=0, return_index=True)
    return p[order[first]]


def build_supports(m: trimesh.Trimesh, spacing: float, base_lift: float, tip_d=0.4, shaft_d=1.0, raft_mm=1.0, envelope=None):
    """Model raised by base_lift; a cone tip + cylinder pillar to a raft under each support point.
    Points whose straight path down hits the model itself are skipped (counted) instead of piercing it."""
    m = m.copy(); m.apply_translation([0, 0, base_lift + raft_mm])
    if envelope is not None:
        envelope = envelope.copy(); envelope.apply_translation([0, 0, base_lift + raft_mm])
    pts = support_points(m, spacing, envelope=envelope)
    parts, skipped = [], 0
    if len(pts):
        org = pts - [0, 0, 0.05]
        hit = m.ray.intersects_any(org, np.tile([0, 0, -1.0], (len(pts), 1)))
        tip_len = 1.2
        for p, h in zip(pts, hit):
            if h:
                skipped += 1; continue
            top = p[2]; bot = raft_mm * 0.5
            if top - tip_len <= bot + 0.2:
                continue
            cone = trimesh.creation.cone(radius=shaft_d / 2, height=tip_len, sections=10)
            cone.apply_transform(trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0]))   # point up
            cone.apply_translation([p[0], p[1], top])
            # tip: truncate visually by a thin contact cylinder
            tipc = trimesh.creation.cylinder(radius=tip_d / 2, height=0.4, sections=8)
            tipc.apply_translation([p[0], p[1], top + 0.1])
            h_shaft = top - tip_len - bot
            shaft = trimesh.creation.cylinder(radius=shaft_d / 2, height=h_shaft + 0.1, sections=10)
            shaft.apply_translation([p[0], p[1], bot + h_shaft / 2])
            parts += [cone, tipc, shaft]
    used = len(parts) // 3
    if used:
        xy = np.array([q.centroid[:2] for q in parts[2::3]])
        lo, hi = xy.min(0) - 3, xy.max(0) + 3
    else:
        lo, hi = m.bounds[0][:2] - 2, m.bounds[1][:2] + 2
    raft = trimesh.creation.box(extents=[hi[0] - lo[0], hi[1] - lo[1], raft_mm])
    raft.apply_translation([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, raft_mm / 2])
    u = union_all([m, raft, *parts])
    if u is not None:                       # one solid: no overlapping shells, and the ml is the real union
        out, extra, merged = u, float(abs(u.volume)) - float(abs(m.volume)), True
    else:
        out, extra, merged = trimesh.util.concatenate([m, raft, *parts]), float(raft.volume + sum(abs(q.volume) for q in parts)), False
    return out, {"_volume": extra, "merged": merged, "supports": used, "skipped_inside": skipped, "raft_mm": raft_mm, "tip_mm": tip_d, "shaft_mm": shaft_d}


def _cavities(m: trimesh.Trimesh):
    """Inside-out shells of a hollowed solid = the cavities (negative volume)."""
    return [c for c in m.split(only_watertight=False) if c.is_watertight and c.volume < 0]


def add_holes(m: trimesh.Trimesh, diameter: float, per_cavity: int = 2):
    """Drain + vent: per sealed cavity, one hole at its plate-side end (lowest z) and one at the far end (highest z),
    each drilled straight through the nearest outer wall. Returns (mesh, holes made per cavity)."""
    cavs = _cavities(m)
    if not cavs or diameter <= 0:
        return m, [0] * len(cavs)
    outer = max(m.split(only_watertight=False), key=lambda c: c.volume)
    made = []
    for cav in cavs:
        v = cav.vertices
        targets = [v[np.argmin(v[:, 2])], v[np.argmax(v[:, 2])]][:per_cavity]
        n = 0
        for t in targets:
            cp, dist, _ = trimesh.proximity.closest_point(outer, [t])
            d = cp[0] - t
            L = float(np.linalg.norm(d))
            if L < 1e-6:
                continue
            axis = d / L
            h = L + 2 * diameter + 1.0
            cyl = trimesh.creation.cylinder(radius=diameter / 2, height=h, sections=32)
            T = trimesh.geometry.align_vectors([0, 0, 1], axis)
            T[:3, 3] = t + axis * (L / 2)
            cyl.apply_transform(T)
            try:
                m = meshedit._boolean(m, cyl, "difference"); n += 1
            except meshedit.OpError:
                pass
        made.append(n)
    return m, made


def layer_check(m: trimesh.Trimesh, step: float = 0.25, max_layers: int = 400) -> dict:
    """Slice the print every `step` mm (z=0 is the build plate) and look for:
    islands: a region with no overlap with the layer before it (starts in mid-air, nothing to hang from);
    suction cups: a hole in the layers that is closed on its plate side (sealed by material or the plate) so every
    peel pulls a vacuum. A hole that reaches open space on the plate side is vented."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    z0, z1 = float(m.bounds[0][2]), float(m.bounds[1][2])
    if z1 - z0 < step * 2:
        return {"islands": [], "suction": []}
    step = max(step, (z1 - z0) / max_layers)
    zs = np.arange(z0 + step / 2, z1, step)
    secs = m.section_multiplane([0, 0, 0], [0, 0, 1], zs)
    layers = []
    for sec in secs:
        polys = []
        if sec is not None:
            try:
                polys = [p.buffer(0) for p in sec.polygons_full if p.area > 1e-4]
            except Exception:
                polys = []
        layers.append(polys)
    islands, holes, parent = [], [], {}
    prev_mat = prev_fill = None
    for i, polys in enumerate(layers):
        mat = unary_union(polys) if polys else None
        fill = unary_union([Polygon(p.exterior) for p in polys]) if polys else None
        for p in polys:
            if i > 0 and (prev_mat is None or not p.intersects(prev_mat)) and p.area > 0.05:
                islands.append({"z_mm": round(float(zs[i]), 2), "area_mm2": round(p.area, 2),
                                "xy": [round(c, 1) for c in p.representative_point().coords[0]]})
            for r in p.interiors:
                h = Polygon(r)
                if h.area < 1.0:
                    continue
                # vented on the plate side if, in the layer below, part of this hole is outside every outline (open vat)
                below_open = i > 0 and (prev_fill is None or h.difference(prev_fill).area > 0.2)
                holes.append({"i": i, "poly": h, "open": below_open})
        prev_mat, prev_fill = mat, fill
    # chain holes across layers by overlap (union-find); a chain is vented if any member opens below
    def find(a):
        while parent.get(a, a) != a:
            a = parent[a]
        return a
    by_layer = {}
    for k, h in enumerate(holes):
        by_layer.setdefault(h["i"], []).append(k)
    for k, h in enumerate(holes):
        for j in by_layer.get(h["i"] - 1, []):
            if holes[j]["poly"].intersects(h["poly"]):
                parent[find(k)] = find(j)
    groups = {}
    for k in range(len(holes)):
        groups.setdefault(find(k), []).append(k)
    suction = []
    for g in groups.values():
        if len(g) < 2 or any(holes[k]["open"] for k in g):
            continue
        first = min(g, key=lambda k: holes[k]["i"])
        suction.append({"z_mm": round(float(zs[holes[first]["i"]]), 2), "layers": len({holes[k]["i"] for k in g}),
                        "area_mm2": round(max(holes[k]["poly"].area for k in g), 1)})
    return {"islands": islands[:50], "suction": suction[:50], "step_mm": round(step, 3)}


def union_all(meshes):
    """One solid from overlapping bodies (model + raft + supports) with manifold3d. None if it can't be done."""
    try:
        import manifold3d as mf
        ms = []
        for q in meshes:
            if len(q.faces) == 0:
                continue
            ms.append(mf.Manifold(mf.Mesh(vert_properties=np.asarray(q.vertices, dtype=np.float32),
                                          tri_verts=np.asarray(q.faces, dtype=np.uint32))))
        u = mf.Manifold.batch_boolean(ms, mf.OpType.Add)
        out = u.to_mesh()
        r = trimesh.Trimesh(vertices=np.asarray(out.vert_properties)[:, :3], faces=np.asarray(out.tri_verts), process=False)
        return r if len(r.faces) and r.is_watertight else None
    except Exception:
        return None


def estimate(height_mm: float, volume_mm3: float, s: dict) -> dict:
    layers = max(1, math.ceil(height_mm / s["layer_mm"] - 1e-9))
    bottom = min(layers, s["bottom_layers"])
    move = 2 * s["lift_mm"] / s["lift_speed_mm_min"] * 60 + 0.5          # up + down + settle
    secs = bottom * s["bottom_exposure_s"] + (layers - bottom) * s["exposure_s"] + layers * move
    ml = volume_mm3 / 1000.0
    price, unit = s.get("price", DEFAULT_PRICE), s.get("price_unit", DEFAULT_PRICE_UNIT)
    cost = ml / 1000.0 * price if unit == "l" else ml * RESIN_DENSITY_G_ML / 1000.0 * price
    return {"cost": round(cost, 2), "cost_note": f"Resin only, at {price:g} per {'litre' if unit == 'l' else 'kg'}"
            + (f" (density {RESIN_DENSITY_G_ML:g} g/ml)" if unit == "kg" else "") + "; leaves out spills, IPA, gloves and failed prints.",
            "layers": layers, "print_seconds": round(secs), "print_time_human": f"{int(secs // 3600)} h {int(secs % 3600 // 60)} min",
            "resin_ml": round(ml, 1), "resin_note": "Resin volume of the model (plus supports); add ~10% for spills and the vat film."}


def prepare(m: trimesh.Trimesh, s: dict, bed_mm=None) -> tuple[trimesh.Trimesh, dict]:
    """The TorchC0 pipeline: tilt -> hollow -> drain + vent holes -> supports + raft -> layer check (islands, suction cups).
    Warnings never block: they are notes; the files are always made."""
    rep = {"program": NAME, "settings": s, "notes": [], "safety": SAFETY, "test_note": TEST_NOTE}
    work = orient(m, s["tilt_deg"])
    envelope = None
    if s["hollow"] and s["wall_mm"] > 0:
        try:
            hollowed, hr = meshedit.op_hollow(work, {"wall": s["wall_mm"], "drain_diameter": 0})
            hollowed, made = add_holes(hollowed, s["drain_mm"])
            envelope = work if work.is_watertight else None
            work = hollowed
            rep["hollow"] = {k: hr[k] for k in ("message", "volume_saved_pct", "thinnest_wall_mm") if k in hr}
            rep["hollow"]["cavities"] = len(made); rep["hollow"]["holes"] = made
            thin = hr.get("wall_min_probe_mm", hr.get("thinnest_wall_mm"))
            if thin is not None and thin < s["wall_mm"] - 0.05:
                rep["hollow"]["thin_wall"] = True
                rep["notes"].append(f"Thin wall: the thinnest wall came out {thin:.2f} mm, thinner than the {s['wall_mm']:g} mm you asked for. "
                                    "Thin spots can crack or leak resin; try a thicker wall if this part must be strong.")
            elif hr.get("note"):
                rep["notes"].append(hr["note"])
            short = sum(1 for n in made if n < 2)
            if short:
                rep["notes"].append(f"{short} hollow space(s) have fewer than 2 holes. Resin needs a drain hole and an air vent "
                                    "to flow out, or it gets trapped and can crack the print. Set the hole size to 2.5 mm or more.")
        except meshedit.OpError as e:
            rep["notes"].append(f"Printed solid (not hollowed): {e}")
    vol = float(abs(work.volume))
    if s["supports"]:
        work, sr = build_supports(work, s["support_spacing_mm"], s["base_lift_mm"], envelope=envelope)
        rep["support"] = sr
        vol += sr.pop("_volume")
        if sr["skipped_inside"]:
            rep["notes"].append(f"{sr['skipped_inside']} overhang spot(s) sit above other parts of the model and got no support; "
                                "check them in your slicer and add supports there if needed.")
    else:
        rep["notes"].append("Supports are off: only flat-bottomed models print without them. Add supports in your slicer otherwise.")
    try:
        lc = layer_check(work)
    except Exception:
        lc = {"islands": [], "suction": []}
    rep["layer_check"] = lc
    if lc["islands"]:
        rep["notes"].append(f"{len(lc['islands'])} island(s): parts that start in mid-air with nothing under them (first at "
                            f"{lc['islands'][0]['z_mm']} mm). They will fail or float in the vat; add supports under them.")
    if lc["suction"]:
        rep["notes"].append(f"{len(lc['suction'])} suction cup(s): a hollow or cup shape sealed on the plate side (first at "
                            f"{lc['suction'][0]['z_mm']} mm). Each peel pulls a vacuum that can rip the print off; add a vent hole or tilt it.")
    ext = work.extents
    rep["size_mm"] = [round(float(x), 1) for x in ext]
    rep["estimate"] = estimate(float(ext[2]), vol, s)
    if bed_mm:
        fits = all(a <= b + 1e-6 for a, b in zip(sorted(ext[:2]), sorted(bed_mm[:2]))) and ext[2] <= bed_mm[2]
        rep["fits"] = bool(fits)
        if not fits:
            rep["notes"].append(f"Too big for this printer ({' × '.join(f'{x:g}' for x in bed_mm)} mm). Scale it down or split it.")
    return work, rep
