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
    """Preset first, then explicit values. Defaults: 30° tilt, 2 mm hollow wall, two 3 mm drain holes, supports on."""
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


def support_points(m: trimesh.Trimesh, spacing: float, max_angle_deg: float = 45.0) -> np.ndarray:
    """Points on downward-facing surfaces (steeper than max_angle_deg from vertical-down counts as overhang),
    thinned to one per `spacing` mm cell, plus every local lowest vertex (islands that would start mid-air)."""
    down = m.face_normals[:, 2] < -math.cos(math.radians(max_angle_deg))
    pts = []
    if down.any():
        area = m.area_faces[down].sum()
        n = int(min(20000, max(50, area / (spacing * spacing) * 4)))
        sub = m.submesh([np.nonzero(down)[0]], append=True)
        p, _ = trimesh.sample.sample_surface_even(sub, n, radius=spacing * 0.5, seed=3) if len(sub.faces) else (np.zeros((0, 3)), None)
        pts.append(p)
    # local minima: vertices lower than all their neighbours
    v = m.vertices; nb = m.vertex_neighbors
    mins = [i for i in range(len(v)) if nb[i] and all(v[i, 2] < v[j, 2] - 1e-9 for j in nb[i])]
    if mins:
        pts.append(v[mins])
    if not pts:
        return np.zeros((0, 3))
    p = np.vstack(pts)
    keys = np.floor(p[:, :2] / spacing).astype(np.int64)
    order = np.lexsort((p[:, 2], keys[:, 1], keys[:, 0]))        # lowest point per cell wins
    _, first = np.unique(keys[order], axis=0, return_index=True)
    return p[order[first]]


def build_supports(m: trimesh.Trimesh, spacing: float, base_lift: float, tip_d=0.4, shaft_d=1.0, raft_mm=1.0):
    """Model raised by base_lift; a cone tip + cylinder pillar to a raft under each support point.
    Points whose straight path down hits the model itself are skipped (counted) instead of piercing it."""
    m = m.copy(); m.apply_translation([0, 0, base_lift + raft_mm])
    pts = support_points(m, spacing)
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
    out = trimesh.util.concatenate([m, raft, *parts])
    return out, {"_volume": float(raft.volume + sum(abs(q.volume) for q in parts)), "supports": used, "skipped_inside": skipped, "raft_mm": raft_mm, "tip_mm": tip_d, "shaft_mm": shaft_d}


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
    """The TorchC0 pipeline: hollow (+drain holes) -> tilt -> supports + raft. Returns (print mesh, report)."""
    rep = {"program": NAME, "settings": s, "notes": [], "safety": SAFETY, "test_note": TEST_NOTE}
    work = m
    if s["hollow"] and s["wall_mm"] > 0:
        try:
            work, hr = meshedit.op_hollow(m, {"wall": s["wall_mm"], "drain_diameter": s["drain_mm"]})
            rep["hollow"] = {k: hr[k] for k in ("message", "volume_saved_pct", "thinnest_wall_mm") if k in hr}
            if hr.get("note"):
                rep["notes"].append(hr["note"])
            if not s["drain_mm"]:
                rep["notes"].append("Hollow without a drain hole traps liquid resin inside. Add a drain hole of 2.5 mm or more.")
        except meshedit.OpError as e:
            work = m
            rep["notes"].append(f"Printed solid (not hollowed): {e}")
    work = orient(work, s["tilt_deg"])
    vol = float(abs(work.volume))
    if s["supports"]:
        work, sr = build_supports(work, s["support_spacing_mm"], s["base_lift_mm"])
        rep["support"] = sr
        vol += sr.pop("_volume")
        if sr["skipped_inside"]:
            rep["notes"].append(f"{sr['skipped_inside']} overhang spot(s) sit above other parts of the model and got no support; "
                                "check them in your slicer and add supports there if needed.")
    else:
        rep["notes"].append("Supports are off: only flat-bottomed models print without them. Add supports in your slicer otherwise.")
    ext = work.extents
    rep["size_mm"] = [round(float(x), 1) for x in ext]
    rep["estimate"] = estimate(float(ext[2]), vol, s)
    if bed_mm:
        fits = all(a <= b + 1e-6 for a, b in zip(sorted(ext[:2]), sorted(bed_mm[:2]))) and ext[2] <= bed_mm[2]
        rep["fits"] = bool(fits)
        if not fits:
            rep["notes"].append(f"Too big for this printer ({' × '.join(f'{x:g}' for x in bed_mm)} mm). Scale it down or split it.")
    return work, rep
