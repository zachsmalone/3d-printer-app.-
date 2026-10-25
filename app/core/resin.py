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
          "Print and wash in a ventilated room; keep resin away from pets, food areas and anyone not wearing gloves.",
          "Wash prints in IPA (or the resin maker's wash), then cure under UV. Cure used IPA and resin waste in sunlight before disposal; never pour it down a drain.",
          "Hollow prints need drain holes, or trapped liquid resin can crack the print later."]
def _data_price():
    """Price per litre from data/resin/resin.json if a resin profile there carries one ("resins"/"profiles" entries with
    price_per_l). None otherwise: TorchC0 never makes up a price; the user types their own."""
    import json
    from pathlib import Path
    try:
        d = json.loads((Path(__file__).resolve().parents[2] / "data" / "resin" / "resin.json").read_text())
    except (OSError, ValueError):
        return None
    for key in ("resins", "profiles", "resin_profiles"):
        for r in d.get(key) or []:
            v = r.get("price_per_l") if isinstance(r, dict) else None
            if isinstance(v, (int, float)) and v > 0:
                return float(v)
    return None


# Density of standard resins is ~1.1 g/ml (1.05-1.25), used only to turn a per-kg price into a per-ml cost.
DEFAULT_PRICE = _data_price()
DEFAULT_PRICE_UNIT = "l"
RESIN_DENSITY_G_ML = 1.1
TEST_NOTE = "Starting values only. Run an exposure test with your resin (most resin makers publish one) and adjust in your slicer."

# Materials are separate from the quality presets above. "standard" keeps using detail/standard/fast.
# "silicone" is a flexible / silicone-like photopolymer. Its starting exposure and lift are one published
# profile, not a universal silicone number: Liqcreate Flexible-X on the original Elegoo Saturn at 50 µm
# (10 s normal, 40 s bottom, lift 10 mm at 60 mm/min).
# https://www.liqcreate.com/supportarticles/resin-settings-elegoo-saturn/
# Bottom layers stay at 5 (the usual count in this program). That page uses 2 bottom layers plus 6
# transition layers, which TorchC0 cannot set separately. No price: nothing here is a silicone price.
# No single density either. Published liquid densities we checked:
#   Resione F69 1.079 g/cm³ (ASTM D4052) — https://www.resione.com/products/f69-black-flexible-rubber-like-3d-printer-resin-1kg
#   Siraya Tech Tenacious Flex Black 1.1 — https://siraya.tech/pages/70a-flexible-resin-tenacious-flex-black-tds
#   Liqcreate Flexible-X 1.18 g/cm³ — https://www.liqcreate.com/product/flexible-x/
DEFAULT_MATERIAL = "standard"
MATERIALS = {
    "standard": {
        "label": "Standard resin",
        "help": "Rigid photopolymer. The fine, standard, and fast presets set the starting layer and exposure.",
        "settings": None,
        "density_g_ml": RESIN_DENSITY_G_ML,
        "price_per_l": None,
        "notes": [],
        "safety": [],
        "sources": [],
    },
    "silicone": {
        "label": "Silicone resin",
        "help": "Flexible, silicone-like photopolymer. Start at 0.05 mm layers, 10 s exposure, 40 s bottom exposure, "
                 "lift 10 mm at 60 mm/min. Those figures are Liqcreate's published Flexible-X profile for the original "
                 "Elegoo Saturn at 50 µm, not a tuned profile for every bottle or newer printer. "
                 "The fine / standard / fast presets are for standard resin.",
        "settings": {"layer_mm": 0.05, "exposure_s": 10.0, "bottom_exposure_s": 40.0, "bottom_layers": 5,
                     "lift_mm": 10.0, "lift_speed_mm_min": 60.0},
        "density_g_ml": None,
        "price_per_l": None,
        "notes": [
            "Other published profiles sit far from these numbers. Resione F69 uses 0.05 mm layers and about 1.2 times that printer's standard exposure. Liqcreate Elastomer-X is 16 s normal and 50 s bottom on the original Saturn, and 14 s and 60 s bottom on a Saturn 4 Ultra (both at 50 µm; on the Ultra they say to use the printer's Slow movement, because lift speed is limited). Siraya Tech publishes a profile per printer for its flexible resins instead of one exposure for every machine.",
            "Wash with the solvent named on the bottle, then let the print dry before UV curing. Liqcreate's flexible-resin guide uses IPA or ethanol: about 2 minutes in used solvent, then 3 minutes in fresh, then dry about 30 minutes. Siraya Tech's Tenacious Flex Black guide uses ethanol or IPA for 2-3 minutes, then dries the print and cures about 10 minutes for a thin part or up to 25 for a thick one. Formlabs Silicone 40A (their own printers) is washed in IPA mixed with n-butyl acetate, or in two IPA sonications of 2-3 minutes, then dried; they pull supports off before curing and post-cure in water.",
            "A soft print tears easily before it is fully cured. Liqcreate asks for heavy supports for Flexible-X and extra-heavy supports for Elastomer-X. Resione asks for thicker, denser supports than for rigid resin, and cures F69 parts thicker than 3 mm for more than 30 minutes per side in a 40 W UV box. Bottom layers stay at 5 here; Liqcreate's Flexible-X profile is 2 bottom layers plus 6 transition layers, which this program cannot set separately.",
        ],
        "safety": [
            "Soft and silicone-like resin irritates skin and eyes too. Wear nitrile gloves and eye protection while washing the print and pulling supports, and use only the wash the resin maker names. A long soak can swell a soft print.",
        ],
        "sources": [
            {"label": "Liqcreate Flexible-X on the original Elegoo Saturn, 50 µm (10 s, 40 s bottom, lift 10 mm at 60 mm/min)",
             "url": "https://www.liqcreate.com/supportarticles/resin-settings-elegoo-saturn/"},
            {"label": "Liqcreate Elastomer-X on the Saturn 4 Ultra, 50 µm (14 s, 60 s bottom, Slow movement)",
             "url": "https://www.liqcreate.com/supportarticles/elegoo-saturn4-ultra-flexible-resin/"},
            {"label": "Resione F69 printing settings (0.05 mm, about 1.2 times standard exposure) and liquid density 1.079 g/cm³",
             "url": "https://www.resione.com/products/f69-black-flexible-rubber-like-3d-printer-resin-1kg"},
            {"label": "Siraya Tech Tenacious Flex Black TDS (liquid density 1.1; ethanol or IPA wash; cure 10-25 min)",
             "url": "https://siraya.tech/pages/70a-flexible-resin-tenacious-flex-black-tds"},
            {"label": "Siraya Tech Rebound 55A: slower lift and a longer light-off for high viscosity",
             "url": "https://siraya.tech/pages/siraya-tech-rebound-55a-black-tds"},
            {"label": "Liqcreate flexible and elastomer resin guide (wash, dry, supports)",
             "url": "https://www.liqcreate.com/supportarticles/instructions-3dprinted-flexible-resin/"},
            {"label": "Liqcreate Flexible-X liquid density 1.18 g/cm³",
             "url": "https://www.liqcreate.com/product/flexible-x/"},
            {"label": "Formlabs: using Silicone 40A (wash, dry, supports before cure, post-cure in water)",
             "url": "https://formlabs.com/support/Using-Silicone-40A-Resin/"},
        ],
    },
}


def public_materials():
    """Catalog rows for the resin material picker. Prices stay null unless a profile actually carries one."""
    rows = []
    for mid, m in MATERIALS.items():
        st = m.get("settings")
        rows.append({
            "id": mid, "label": m["label"], "help": m["help"],
            "settings": dict(st) if st else None,
            "notes": list(m["notes"]), "safety": list(m["safety"]),
            "sources": [dict(s) for s in m["sources"]],
            "density_g_ml": m["density_g_ml"], "price_per_l": m.get("price_per_l"),
        })
    return rows


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


def _material_price(o, material):
    """User-typed price wins. A saved price applies only to standard resin, and only when data/resin/resin.json has one.
    Silicone has no sourced price, so an empty field stays empty."""
    fallback = MATERIALS[material].get("price_per_l")
    if fallback is None and material == "standard":
        fallback = DEFAULT_PRICE
    if o.get("price") in (None, "") and fallback is None:
        return None
    return _num(o, "price", 0 if fallback is None else fallback)


def settings(opts: dict | None = None) -> dict:
    """Material, then preset, then explicit values. A silicone profile replaces the quality preset's exposure and lift.
    Defaults: 30° tilt, 2 mm hollow wall, 3 mm drain + vent holes, supports on."""
    o = dict(opts or {})
    material = o.get("material") or DEFAULT_MATERIAL
    if material not in MATERIALS:
        raise ResinError("Unknown resin material.")
    preset = o.get("preset") or DEFAULT_PRESET
    if preset not in PRESETS:
        raise ResinError("Unknown TorchC0 preset.")
    mat = MATERIALS[material]
    base = mat["settings"] if mat.get("settings") else PRESETS[preset]
    s = {"preset": preset, "material": material}
    for k in ("layer_mm", "exposure_s", "bottom_exposure_s", "lift_mm", "lift_speed_mm_min"):
        s[k] = _num(o, k, base[k])
    s["bottom_layers"] = _num(o, "bottom_layers", base["bottom_layers"], int)
    s["tilt_deg"] = _num(o, "tilt_deg", 30.0)
    s["wall_mm"] = _num(o, "wall_mm", 2.0)
    s["drain_mm"] = _num(o, "drain_mm", 3.0)
    s["support_spacing_mm"] = _num(o, "support_spacing_mm", 4.0)
    s["base_lift_mm"] = _num(o, "base_lift_mm", 5.0)
    s["density_g_ml"] = mat["density_g_ml"]
    s["price"] = _material_price(o, material)
    s["price_unit"] = o.get("price_unit") or DEFAULT_PRICE_UNIT
    if s["price_unit"] not in ("l", "kg"):
        raise ResinError("Price unit must be per litre (l) or per kg.")
    s["hollow"] = str(o.get("hollow", "true")).lower() in ("1", "true", "on", "yes")
    s["supports"] = str(o.get("supports", "true")).lower() in ("1", "true", "on", "yes")
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


def build_supports(m: trimesh.Trimesh, spacing: float, base_lift: float, tip_d=0.4, shaft_d=1.0, raft_mm=1.0, envelope=None,
                   extra=None, auto=True):
    """Model raised by base_lift; a cone tip + cylinder pillar to a raft under each support point.
    Points whose straight path down hits the model itself are skipped (counted) instead of piercing it."""
    m = m.copy(); m.apply_translation([0, 0, base_lift + raft_mm])
    if envelope is not None:
        envelope = envelope.copy(); envelope.apply_translation([0, 0, base_lift + raft_mm])
    pts = support_points(m, spacing, envelope=envelope) if auto else np.zeros((0, 3))
    if extra is not None and len(extra):          # user-asked points (islands), given before the lift
        ex = _surface_below(m, np.asarray(extra, dtype=float) + [0, 0, base_lift + raft_mm])
        pts = np.vstack([pts, ex]) if len(pts) else ex
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
            # taper: wide end on the pillar, point up into the contact tip (the old cone pointed down and met the
            # pillar at a single vertex, which is not a solid joint and fell apart into pieces after export)
            cone = trimesh.creation.cone(radius=shaft_d / 2, height=tip_len, sections=10)
            cone.apply_translation([p[0], p[1], top - tip_len])
            # contact tip: a thin cylinder reaching 0.3 mm into the model so the joint is a real overlap
            tipc = trimesh.creation.cylinder(radius=tip_d / 2, height=0.4, sections=8)
            tipc.apply_translation([p[0], p[1], top + 0.1])
            h_shaft = top - tip_len - bot
            shaft = trimesh.creation.cylinder(radius=shaft_d / 2, height=h_shaft + 0.1, sections=10)
            shaft.apply_translation([p[0], p[1], bot + h_shaft / 2 + 0.05])   # bottom flush with the raft / plate, 0.1 mm into the cone
            parts += [cone, tipc, shaft]
    used = len(parts) // 3
    if used:
        xy = np.array([q.centroid[:2] for q in parts[2::3]])
        lo, hi = xy.min(0) - 3, xy.max(0) + 3
    else:
        lo, hi = m.bounds[0][:2] - 2, m.bounds[1][:2] + 2
    rafts = []
    if raft_mm > 0:
        raft = trimesh.creation.box(extents=[hi[0] - lo[0], hi[1] - lo[1], raft_mm])
        raft.apply_translation([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, raft_mm / 2])
        rafts = [raft]
    u = union_all([m, *rafts, *parts])
    if u is not None:                       # one solid: no overlapping shells, and the ml is the real union
        out, extra, merged = u, float(abs(u.volume)) - float(abs(m.volume)), True
    else:
        out, extra, merged = trimesh.util.concatenate([m, *rafts, *parts]), float(sum(r.volume for r in rafts) + sum(abs(q.volume) for q in parts)), False
    return out, {"_volume": extra, "merged": merged, "bodies": bodies(out), "watertight": bool(merged or _weld_check(out)), "supports": used, "skipped_inside": skipped, "raft_mm": raft_mm, "tip_mm": tip_d, "shaft_mm": shaft_d}


def _surface_below(m, pts, reach=2.0):
    """Snap each point to the model's underside straight below/above it (the island's bottom face), so a tip lands on it."""
    out = []
    for p in pts:
        org = p + [0, 0, reach]
        loc, _, _ = m.ray.intersects_location([org], [[0, 0, -1.0]])
        loc = [q for q in loc if q[2] >= p[2] - reach]
        out.append(min(loc, key=lambda q: q[2]) if loc else p)
    return np.array(out).reshape(-1, 3)


def drill_vent(m: trimesh.Trimesh, at, diameter: float):
    """One vent/drain hole from a point inside an open pocket (a suction cup) out to the open vat or air: try straight
    down (the plate side, where it is sealed) then the four sideways directions, and drill the shortest way that
    passes through one wall and comes out on the outside above the plate. Returns (mesh, made?)."""
    p = np.asarray(at, dtype=float)
    best = None
    for d in ([0, 0, -1.0], [1.0, 0, 0], [-1.0, 0, 0], [0, 1.0, 0], [0, -1.0, 0]):
        loc, _, _ = m.ray.intersects_location([p], [d])
        if len(loc) < 2:
            continue
        t = sorted(float(np.dot(q - p, d)) for q in loc)
        t = [x for x in t if x > 1e-6]
        if len(t) < 2:
            continue
        exit_pt = p + np.asarray(d) * t[1]
        if exit_pt[2] < m.bounds[0][2] + 1e-3:       # comes out on the plate: no way to drain there
            continue
        if best is None or t[1] < best[1]:
            best = (np.asarray(d), t[1])
    if best is None or diameter <= 0:
        return m, False
    d, L = best
    h = L + 2.0
    cyl = trimesh.creation.cylinder(radius=diameter / 2, height=h, sections=24)
    T = trimesh.geometry.align_vectors([0, 0, 1], d)
    T[:3, 3] = p + d * (L / 2)
    cyl.apply_transform(T)
    try:
        return meshedit._boolean(m, cyl, "difference"), True
    except meshedit.OpError:
        return m, False


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
                c = p.representative_point().coords[0]
                islands.append({"z_mm": round(float(zs[i]), 2), "area_mm2": round(p.area, 2),
                                "xy": [round(c[0], 1), round(c[1], 1)], "xyz": [round(c[0], 2), round(c[1], 2), round(float(zs[i]), 2)]})
            for r in p.interiors:
                h = Polygon(r)
                if h.area < 1.0:
                    continue
                # vented on the plate side if, in the layer below, part of this hole is outside every outline (open vat)
                below_open = i > 0 and (prev_fill is None or h.difference(prev_fill).area > 0.2)
                holes.append({"i": i, "poly": h, "open": below_open, "xy": h.representative_point().coords[0]})
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
        h0 = holes[first]
        suction.append({"z_mm": round(float(zs[h0["i"]]), 2), "layers": len({holes[k]["i"] for k in g}),
                        "area_mm2": round(max(holes[k]["poly"].area for k in g), 1),
                        "xyz": [round(float(h0["xy"][0]), 2), round(float(h0["xy"][1]), 2), round(float(zs[h0["i"]]), 2)]})
    return {"islands": islands[:50], "suction": suction[:50], "step_mm": round(step, 3)}


def _weld_check(r: trimesh.Trimesh) -> bool:
    """True if the mesh survives an STL round trip (float32, vertices welded by position) as a watertight solid."""
    q = trimesh.Trimesh(vertices=np.asarray(r.vertices, dtype=np.float32).astype(np.float64), faces=r.faces, process=True)
    return bool(len(q.faces)) and q.is_watertight and q.is_winding_consistent


def union_all(meshes, tol: float = 1e-3):
    """One solid from overlapping bodies (model + raft + supports, or the overlapping shells of an input file) with a
    real manifold3d boolean union. Slivers and near-duplicate vertices below `tol` mm are simplified away so the result
    stays watertight after STL/3MF export (float32, welded vertices). None if it can't be done."""
    try:
        import manifold3d as mf
        ms = []
        for q in meshes:
            if len(q.faces) == 0:
                continue
            ms.append(mf.Manifold(mf.Mesh64(vert_properties=np.asarray(q.vertices, dtype=np.float64),
                                            tri_verts=np.asarray(q.faces, dtype=np.uint64))))
        if not ms:
            return None
        u = mf.Manifold.batch_boolean(ms, mf.OpType.Add) if len(ms) > 1 else ms[0]
        u = u.simplify(tol)
        if u.is_empty():
            return None
        out = u.to_mesh64()
        r = trimesh.Trimesh(vertices=np.asarray(out.vert_properties)[:, :3], faces=np.asarray(out.tri_verts, dtype=np.int64), process=True)
        return r if len(r.faces) and r.is_watertight and _weld_check(r) else None
    except Exception:
        return None


def bridge_touching(m: trimesh.Trimesh, gap: float = 0.3, r: float = 0.8):
    """Parts that only touch (a head resting on a body at one point) stay separate after a union and print as loose
    pieces. Join each part lying within `gap` mm of a bigger one with a small ball at the touching point.
    Returns (mesh, bridges made)."""
    parts = sorted(m.split(only_watertight=False), key=lambda q: -abs(q.volume))
    if len(parts) < 2:
        return m, 0
    balls = []
    for small in parts[1:]:
        best = None
        for big in parts:
            if big is small:
                continue
            cp, dist, _ = trimesh.proximity.closest_point(big, small.vertices)
            k = int(np.argmin(dist))
            if best is None or dist[k] < best[0]:
                best = (float(dist[k]), (cp[k] + small.vertices[k]) / 2)
        if best and best[0] <= gap:
            balls.append(trimesh.creation.icosphere(subdivisions=2, radius=r).apply_translation(best[1]))
    if not balls:
        return m, 0
    u = union_all([m, *balls])
    return (u, len(balls)) if u is not None else (m, 0)


def bodies(m: trimesh.Trimesh) -> int:
    """Separate pieces as a slicer sees them after export (vertices welded by position)."""
    q = trimesh.Trimesh(vertices=np.asarray(m.vertices, dtype=np.float32).astype(np.float64), faces=m.faces, process=True)
    return len(q.split(only_watertight=False))


THIN_ASK_NOTE = ("Hollow wall under 1 mm: walls this thin crack easily in resin. Prepared anyway as you asked; "
                 "use 1 mm or more, or turn hollowing off, if the part must be strong.")


def thin_wall_note(thin: float, asked: float) -> str:
    return (f"Thin wall: the thinnest wall came out {thin:.2f} mm, thinner than the {asked:g} mm you asked for. "
            "Thin spots can crack or leak resin; try a thicker wall if this part must be strong.")


def cost_of(ml: float, price, unit: str = "l", density: float | None = RESIN_DENSITY_G_ML) -> dict:
    """Resin cost estimate for `ml` millilitres at the user's price per litre (or per kg). No price -> no cost.
    Per-kg needs a density. Silicone passes None: published liquid densities differ, so no cost is invented."""
    if price is None:
        return {"cost": None, "cost_note": "Enter your resin's price (per litre or kg) to see a cost estimate."}
    if unit == "kg" and density is None:
        return {"cost": None, "cost_note": "No silicone density is applied here. Published liquid densities differ "
                "(Resione F69 lists 1.079 g/cm³, Siraya Tech Tenacious Flex Black lists 1.1, Liqcreate Flexible-X lists 1.18). "
                "Enter a price per litre."}
    dens = RESIN_DENSITY_G_ML if density is None else density
    cost = ml / 1000.0 * price if unit == "l" else ml * dens / 1000.0 * price
    return {"cost": round(cost, 2), "cost_note": f"Estimate: resin only, at {price:g} per {'litre' if unit == 'l' else 'kg'}"
            + (f" (density {dens:g} g/ml)" if unit == "kg" else "") + "; leaves out spills, IPA, gloves and failed prints."}


def estimate(height_mm: float, volume_mm3: float, s: dict) -> dict:
    layers = max(1, math.ceil(height_mm / s["layer_mm"] - 1e-9))
    bottom = min(layers, s["bottom_layers"])
    move = 2 * s["lift_mm"] / s["lift_speed_mm_min"] * 60 + 0.5          # up + down + settle
    secs = bottom * s["bottom_exposure_s"] + (layers - bottom) * s["exposure_s"] + layers * move
    ml = volume_mm3 / 1000.0
    return {**cost_of(ml, s.get("price", DEFAULT_PRICE), s.get("price_unit", DEFAULT_PRICE_UNIT), s.get("density_g_ml", RESIN_DENSITY_G_ML)),
            "layers": layers, "print_seconds": round(secs), "print_time_human": f"{int(secs // 3600)} h {int(secs % 3600 // 60)} min",
            "resin_ml": round(ml, 1), "resin_note": "Resin volume of the model (plus supports); add ~10% for spills and the vat film."}


def prepare(m: trimesh.Trimesh, s: dict, bed_mm=None, island_supports=None, drains=None) -> tuple[trimesh.Trimesh, dict]:
    """The TorchC0 pipeline: tilt -> hollow -> drain + vent holes -> supports + raft -> layer check (islands, suction cups).
    Warnings never block: they are notes; the files are always made."""
    mat = MATERIALS[s.get("material") or DEFAULT_MATERIAL]
    rep = {"program": NAME, "settings": s, "notes": [], "safety": list(SAFETY) + list(mat["safety"]), "test_note": TEST_NOTE,
           "material": {"id": s.get("material") or DEFAULT_MATERIAL, "label": mat["label"]},
           "material_notes": list(mat["notes"])}
    work = orient(m, s["tilt_deg"])
    shells = work.split(only_watertight=False)
    if len(shells) > 1:
        # overlapping bodies: join them FIRST, so hollowing sees one solid (not shells inside shells) and the shared
        # volume is counted once
        u = union_all(shells)
        if u is not None and bodies(u) > 1:
            u, nb = bridge_touching(u)
            if nb:
                rep["bridged"] = nb
        if u is not None:
            rep["input_union"] = {"bodies_in": len(shells), "bodies_out": bodies(u)}
            work = u
        else:
            rep["notes"].append(f"The model has {len(shells)} separate or overlapping bodies that could not be joined into "
                                "one solid; overlapping parts may hollow badly and their resin may be counted twice.")
    envelope = None
    if s["hollow"] and 0 < s["wall_mm"] < 1.0:
        rep["notes"].append(THIN_ASK_NOTE)          # a warning, never a refusal (warnings never block)
    if s["hollow"] and s["wall_mm"] > 0:
        try:
            hollowed, hr = meshedit.op_hollow(work, {"wall": s["wall_mm"], "drain_diameter": 0})
            hollowed, made = add_holes(hollowed, s["drain_mm"])
            envelope = work if work.is_watertight else None
            work = hollowed
            rep["hollow"] = {k: hr[k] for k in ("message", "volume_saved_pct", "thinnest_wall_mm") if k in hr}
            # one number everywhere: the note and the report both show the probe's thinnest spot (was 0.02 mm apart)
            if hr.get("wall_min_probe_mm") is not None:
                rep["hollow"]["thinnest_wall_mm"] = hr["wall_min_probe_mm"]
            rep["hollow"]["cavities"] = len(made); rep["hollow"]["holes"] = made
            thin = hr.get("wall_min_probe_mm", hr.get("thinnest_wall_mm"))
            if thin is not None and thin < s["wall_mm"] - 0.05:
                # one wording for every thin-wall case (meshedit's own note says the same thing differently: not used)
                rep["hollow"]["thin_wall"] = True
                rep["notes"].append(thin_wall_note(thin, s["wall_mm"]))
            short = sum(1 for n in made if n < 2)
            if short:
                rep["notes"].append(f"{short} hollow space(s) have fewer than 2 holes. Resin needs a drain hole and an air vent "
                                    "to flow out, or it gets trapped and can crack the print. Set the hole size to 2.5 mm or more.")
        except meshedit.OpError as e:
            # meshedit's text ends "Try a thinner wall." for its own tool; here it would contradict the 1 mm advice
            why = str(e).replace(" Try a thinner wall.", "").replace(" Try a different wall thickness.", "")
            rep["notes"].append(f"Printed solid (not hollowed): {why} A part this small or thin prints fine solid.")
    if drains:                                   # one-click "Add drain hole" for suction cups (points in the model frame)
        made = 0
        for at in drains[:20]:
            work, ok = drill_vent(work, at, s["drain_mm"] or 2.0)
            made += ok
        rep["drains_added"] = made
        if made < len(drains[:20]):
            rep["notes"].append(f"{len(drains[:20]) - made} drain hole(s) could not be drilled (no wall to the outside "
                                "above the plate there); tilt the model or turn supports on so the cup lifts off the plate.")
    lift = 0.0
    vol = float(abs(work.volume))
    if s["supports"] or island_supports:
        # supports off + island pillars only: the model stays on the plate (no lift, no raft); pillars stand on the plate
        bl, raft = (s["base_lift_mm"], 1.0) if s["supports"] else (0.0, 0.0)
        lift = bl + raft
        work, sr = build_supports(work, s["support_spacing_mm"], bl, raft_mm=raft, envelope=envelope,
                                  extra=island_supports[:200] if island_supports else None, auto=s["supports"])
        if island_supports:
            sr["island_supports"] = len(island_supports[:200])
        rep["support"] = sr
        vol += sr.pop("_volume")
        if not sr["merged"]:
            rep["notes"].append("Supports could not be joined to the model into one solid; the file has separate overlapping "
                                "pieces. Most resin slicers still print it, but check it there.")
        if sr["skipped_inside"]:
            rep["notes"].append(f"{sr['skipped_inside']} overhang spot(s) sit above other parts of the model and got no support; "
                                "check them in your slicer and add supports there if needed.")
    if not s["supports"] and not island_supports:
        rep["notes"].append("Supports are off: only flat-bottomed models print without them. Add supports in your slicer otherwise.")
    try:
        lc = layer_check(work, step=s["layer_mm"])      # sliced at the chosen layer height (capped at 400 slices)
    except Exception:
        lc = {"islands": [], "suction": []}
    # markers for the 3D view are in the output frame; "at" is the same point in the model frame (before the support
    # lift) so the UI can send it back for "Add supports to islands" / "Add drain hole"
    for it in lc["islands"] + lc["suction"]:
        if "xyz" in it:
            it["at"] = [it["xyz"][0], it["xyz"][1], round(it["xyz"][2] - lift, 2)]
    lc["lift_mm"] = lift
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
