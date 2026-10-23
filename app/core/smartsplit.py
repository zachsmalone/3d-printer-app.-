"""Smart Split: auto-cut a model so each piece fits the chosen printer's bed, with join options.

Join connectors (magnet pockets, dovetail tabs, alignment pins, plain glue faces) use starting
sizes from data/split/split-specs.json. Fit is always labelled Simulated until a real test print
is logged — never claimed as verified.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np
import trimesh

from . import meshedit
from . import orient

SPECS_PATH = Path(__file__).resolve().parents[2] / "data" / "split" / "split-specs.json"
MARGIN_MM = 2.0          # leave a little room inside the advertised bed
GAP_MM = 5.0
MAX_PARTS = 16
MAX_CUTS = 8
JOIN_KINDS = ("glue", "magnet", "dovetail", "pin")
SIMULATED = "Simulated"  # honest label until Ren / Zach logs a real test print


class SplitError(meshedit.OpError):
    pass


@lru_cache(maxsize=1)
def specs() -> dict:
    return json.loads(SPECS_PATH.read_text(encoding="utf-8"))


def bed_for(printer_id=None) -> tuple[str, tuple[float, float, float], str]:
    """Resolved printer id, bed XYZ mm, and public name."""
    from app.services import print_setup as ps
    try:
        pid, _ = ps.resolve(printer_id, None)
    except ps.SetupError as e:
        raise SplitError(str(e)) from e
    bed = ps.bed_of(pid)
    name = ps.printer_public(pid)["name"]
    return pid, (float(bed[0]), float(bed[1]), float(bed[2])), name


def usable_bed(bed: tuple[float, float, float]) -> tuple[float, float, float]:
    return tuple(max(1.0, b - MARGIN_MM) for b in bed)


def fits_bed(size, bed) -> bool:
    u = usable_bed(bed)
    return all(float(s) <= u[i] + 1e-6 for i, s in enumerate(size[:3]))


def _axis_i(axis: str) -> int:
    if axis not in ("x", "y", "z"):
        raise SplitError("axis must be x | y | z")
    return {"x": 0, "y": 1, "z": 2}[axis]


def plan_cuts(size, bed) -> list[dict]:
    """Evenly spaced axis-aligned cuts so each resulting slab fits usable bed. Empty if already fits."""
    u = usable_bed(bed)
    size = [float(v) for v in size[:3]]
    if fits_bed(size, bed):
        return []
    # Greedy: repeatedly cut the most-oversize axis of the current virtual box.
    # Track the set of piece sizes as a list of extents (axis-aligned only — honest for box-like parts).
    pieces = [list(size)]
    cuts_global: list[dict] = []  # relative: we re-derive absolute positions from the original mesh later
    # Plan as (axis, fraction_from_lo) within the original bounding box — applied on the live mesh.
    # Simpler equivalent: for each oversize axis of the whole model, place cuts at usable intervals.
    lo_frac_cuts: list[tuple[str, float]] = []  # (axis, position as fraction of original extent along that axis, 0..1)
    for ai, ax in enumerate("xyz"):
        if size[ai] <= u[ai] + 1e-6:
            continue
        n = min(MAX_CUTS + 1, max(2, math.ceil(size[ai] / u[ai])))
        # n pieces => n-1 cuts at i/n of the extent
        for i in range(1, n):
            lo_frac_cuts.append((ax, i / n))
    # Cap total cuts
    lo_frac_cuts = lo_frac_cuts[:MAX_CUTS]
    # Convert to absolute positions once we know mesh bounds (caller does that).
    return [{"axis": ax, "t": t} for ax, t in lo_frac_cuts]


def absolute_cuts(mesh: trimesh.Trimesh, plan: list[dict]) -> list[dict]:
    lo, hi = mesh.bounds
    out = []
    for c in plan:
        i = _axis_i(c["axis"])
        pos = float(lo[i] + (hi[i] - lo[i]) * c["t"])
        out.append({"axis": c["axis"], "position": pos})
    return out


def _slice_one(m: trimesh.Trimesh, axis: str, position: float) -> tuple[trimesh.Trimesh, trimesh.Trimesh, np.ndarray]:
    """Split into (below, above) relative to axis+position. Normal points toward the +axis side."""
    i = _axis_i(axis)
    normal = np.eye(3)[i]
    origin = normal * position
    mm = m
    if not m.is_watertight:
        mm, _ = meshedit.apply(m, "repair", {"keep_largest": False})
    cap = bool(mm.is_watertight)

    def side(n):
        a = mm.slice_plane(origin, n, cap=cap)
        if a is None or not len(a.faces):
            return None
        a = meshedit._new(a.vertices, a.faces)
        if cap and not a.is_watertight and meshedit.have_boolean():
            try:
                L = float(np.linalg.norm(mm.extents)) * 2 + 10
                box = trimesh.creation.box(extents=(L, L, L))
                box = meshedit._transform(meshedit._new(box.vertices, box.faces),
                                          trimesh.geometry.align_vectors([0, 0, 1], n))
                box = meshedit._transform(box, meshedit._mat_translate(np.asarray(origin, float) + n * (L / 2)))
                b2 = meshedit._boolean(mm, box, "intersection")
                if b2.is_watertight:
                    return b2
            except meshedit.OpError:
                pass
        return a

    below = side(-normal)
    above = side(normal)
    if below is None or above is None:
        raise SplitError("The plane doesn't cut through the model (nothing left on one side).")
    return below, above, normal


def _inplane_axes(normal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n = normal / (np.linalg.norm(normal) or 1)
    # Pick a stable in-plane basis
    ref = np.array([0.0, 0.0, 1.0]) if abs(n[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    u = np.cross(n, ref); u /= (np.linalg.norm(u) or 1)
    v = np.cross(n, u); v /= (np.linalg.norm(v) or 1)
    return u, v


def _face_points(mesh: trimesh.Trimesh, origin: np.ndarray, normal: np.ndarray, n: int = 2) -> list[np.ndarray]:
    """n points on the cut face, spaced along the longer in-plane extent, inset from edges."""
    u, v = _inplane_axes(normal)
    # Project vertices near the plane onto (u,v)
    pts = mesh.vertices
    dist = (pts - origin) @ normal
    near = pts[np.abs(dist) < 0.6]
    if len(near) < 3:
        near = pts
    cu = near @ u
    cv = near @ v
    umin, umax = float(cu.min()), float(cu.max())
    vmin, vmax = float(cv.min()), float(cv.max())
    uc = 0.5 * (umin + umax)
    vc = 0.5 * (vmin + vmax)
    if (umax - umin) >= (vmax - vmin):
        span = umax - umin
        inset = min(8.0, max(2.0, span * 0.2))
        if n <= 1 or span < inset * 2 + 1:
            return [origin + u * uc + v * vc]
        xs = np.linspace(umin + inset, umax - inset, n)
        return [origin + u * x + v * vc for x in xs]
    span = vmax - vmin
    inset = min(8.0, max(2.0, span * 0.2))
    if n <= 1 or span < inset * 2 + 1:
        return [origin + u * uc + v * vc]
    ys = np.linspace(vmin + inset, vmax - inset, n)
    return [origin + u * uc + v * y for y in ys]


def _cyl_along(normal, center, radius, height, toward_sign: float) -> trimesh.Trimesh:
    """Cylinder of `height` whose axis is ±normal; the face at `center` is the open end toward -toward_sign*normal."""
    n = normal / (np.linalg.norm(normal) or 1)
    cyl = trimesh.creation.cylinder(radius=radius, height=height, sections=48)
    # default cylinder along +Z, centred at origin spanning -h/2..+h/2
    R = trimesh.geometry.align_vectors([0, 0, 1], n * toward_sign)
    cyl = meshedit._transform(meshedit._new(cyl.vertices, cyl.faces), R)
    # move so the end at -toward_sign sits on `center`, body extending into +toward_sign
    cyl = meshedit._transform(cyl, meshedit._mat_translate(center + n * toward_sign * (height / 2)))
    return cyl


def _add_magnet(below, above, origin, normal, p: dict) -> tuple:
    """Blind pockets on both faces (glue-fit). Defaults: 6×3 mm magnet, PLA clearance from specs."""
    mag_d = meshedit._num(p, "magnet_diameter", 6.0, 2.0, 30.0)
    mag_t = meshedit._num(p, "magnet_thickness", 3.0, 0.5, 20.0)
    clear = meshedit._num(p, "clearance", 0.25, 0.05, 1.0)
    count = int(meshedit._num(p, "count", 2, 1, 6))
    r = (mag_d + clear) / 2
    depth = mag_t + 0.15
    pts = _face_points(below if len(below.vertices) >= len(above.vertices) else above, origin, normal, count)
    for pt in pts:
        # below sits on -normal side: pocket opens toward +normal (into below from the cut)
        hole_b = _cyl_along(normal, pt, r, depth, toward_sign=-1.0)
        # above on +normal side: pocket opens toward -normal
        hole_a = _cyl_along(normal, pt, r, depth, toward_sign=+1.0)
        below = meshedit._boolean(below, hole_b, "difference")
        above = meshedit._boolean(above, hole_a, "difference")
    return below, above, {"magnet_mm": [mag_d, mag_t], "clearance_mm": clear, "pockets": len(pts),
                          "at": [[round(float(c), 3) for c in pt] for pt in pts]}


def _add_pin(below, above, origin, normal, p: dict) -> tuple:
    """Printed pins on the below face, matching holes on the above face."""
    pin_d = meshedit._num(p, "pin_diameter", 4.0, 1.5, 12.0)
    engage = meshedit._num(p, "engagement", 6.0, 2.0, 20.0)
    clear = meshedit._num(p, "clearance", 0.2, 0.05, 1.0)
    count = int(meshedit._num(p, "count", 2, 1, 4))
    half = engage / 2
    pts = _face_points(below, origin, normal, count)
    for pt in pts:
        pin = _cyl_along(normal, pt, pin_d / 2, half, toward_sign=+1.0)  # protrudes into +normal (into above's space)
        # shift so pin starts at the face and goes into above: center at face, toward +normal
        # _cyl_along with toward=+1 places body on +normal side of face — union onto below? 
        # Better: pin is attached to below, protruding in +normal direction.
        pin = _cyl_along(normal, pt, pin_d / 2, half, toward_sign=+1.0)
        # Add a short root into below so it unions solidly
        root = _cyl_along(normal, pt, pin_d / 2, 1.2, toward_sign=-1.0)
        below = meshedit._boolean(below, pin, "union")
        below = meshedit._boolean(below, root, "union")
        hole = _cyl_along(normal, pt, (pin_d + clear) / 2, half + 0.4, toward_sign=+1.0)
        above = meshedit._boolean(above, hole, "difference")
    return below, above, {"pin_diameter_mm": pin_d, "engagement_mm": engage, "clearance_mm": clear, "pins": len(pts),
                          "at": [[round(float(c), 3) for c in pt] for pt in pts]}


def _dovetail_prism(origin, normal, u, length, depth, mouth, root, into_sign: float) -> trimesh.Trimesh:
    """Trapezoidal prism sitting on the cut face, extending `into_sign`*normal into that part."""
    n = normal / (np.linalg.norm(normal) or 1)
    # Cross-section in (along-u, into-part) — extrude along v (perpendicular in plane)
    # Mouth at the face (wider), root deeper inside (narrower) for a locking tab on the male.
    # Male: mouth at face width=mouth, root inside width=root (root < mouth for classic dovetail that locks when slid along v).
    # Build by extruding a 2D trapezoid in the n-u plane, then extruding along v.
    half_m, half_r = mouth / 2, root / 2
    # Local coords: X=u, Y=into (n*into_sign), Z=v
    # Trapezoid points (u, into): at into=0 (face): ±half_m; at into=depth: ±half_r
    from shapely.geometry import Polygon
    poly = Polygon([
        (-half_m, 0), (half_m, 0), (half_r, depth), (-half_r, depth),
    ])
    if not poly.is_valid or poly.area <= 0:
        raise SplitError("Dovetail geometry is invalid for these sizes.")
    # Extrude along Z by `length`, then map local (x,y,z)=(u, into, v) into world
    prism = trimesh.creation.extrude_polygon(poly, length)
    # extrude_polygon: 2D in XY, extrude +Z. So local x=u, y=into, z=v.
    # Rebase so z is centred on 0
    prism.apply_translation([0, 0, -length / 2])
    # Map local basis -> world: x->u, y->n*into_sign, z->cross
    v = np.cross(n, u); v /= (np.linalg.norm(v) or 1)
    into = n * into_sign
    M = np.eye(4)
    M[:3, 0] = u
    M[:3, 1] = into
    M[:3, 2] = v
    M[:3, 3] = origin
    prism = meshedit._transform(meshedit._new(prism.vertices, prism.faces), M)
    return prism


def _add_dovetail(below, above, origin, normal, p: dict) -> tuple:
    sp = specs()["dovetails"]["starting_geometry"]
    depth = meshedit._num(p, "depth", sp["depth_mm"], 1.0, 20.0)
    root = meshedit._num(p, "root_width", sp["root_width_mm"], 2.0, 40.0)
    mouth = meshedit._num(p, "mouth_width", sp["mouth_width_mm"], 2.0, 50.0)
    clear = meshedit._num(p, "clearance", 0.15, 0.05, 1.0)
    if mouth < root:
        mouth, root = root, mouth
    u, v = _inplane_axes(normal)
    # Length along the longer in-plane direction of the face
    pts = below.vertices
    dist = (pts - origin) @ normal
    near = pts[np.abs(dist) < 0.6]
    if len(near) < 3:
        near = pts
    cu = near @ u
    cv = near @ v
    span = float(cv.max() - cv.min())          # the tab runs along v (it is extruded along v), so size it from the v extent
    length = max(8.0, min(span * 0.45, 40.0))
    # Centre the tab on the cut face (not on the world axis): models are not always centred on (0, 0)
    origin = np.asarray(origin, float)
    origin = origin - u * (origin @ u) - v * (origin @ v) + u * 0.5 * float(cu.min() + cu.max()) + v * 0.5 * float(cv.min() + cv.max())
    # Male on below (+normal into the gap / toward above): tab protrudes +normal
    male = _dovetail_prism(origin, normal, u, length, depth, mouth, root, into_sign=+1.0)
    # Female in above: slightly larger pocket opening toward -normal (into above from face = +normal direction from origin into above)
    female = _dovetail_prism(origin, normal, u, length + 0.2,
                             depth + clear, mouth + 2 * clear, root + 2 * clear, into_sign=+1.0)
    below = meshedit._boolean(below, male, "union")
    above = meshedit._boolean(above, female, "difference")
    return below, above, {"depth_mm": depth, "mouth_mm": mouth, "root_mm": root, "clearance_mm": clear, "length_mm": round(length, 2),
                          "at": [[round(float(c), 3) for c in origin]]}


def _add_glue_marks(below, above, origin, normal, p: dict) -> tuple:
    """Tiny registration dimples (male/female) so glue faces line up. Plain flat faces otherwise."""
    count = int(meshedit._num(p, "count", 2, 1, 4))
    r = 1.2
    pts = _face_points(below, origin, normal, count)
    for pt in pts:
        bump = trimesh.creation.icosphere(subdivisions=2, radius=r)
        bump = meshedit._new(bump.vertices + pt + normal * (r * 0.35), bump.faces)
        hole = trimesh.creation.icosphere(subdivisions=2, radius=r + 0.15)
        hole = meshedit._new(hole.vertices + pt + normal * (r * 0.35), hole.faces)
        try:
            below = meshedit._boolean(below, bump, "union")
            above = meshedit._boolean(above, hole, "difference")
        except meshedit.OpError:
            pass  # leave plain face if a mark fails
    return below, above, {"registration_marks": len(pts)}


def apply_join(below, above, origin, normal, join: str, p: dict) -> tuple:
    join = (join or "glue").lower()
    if join not in JOIN_KINDS:
        raise SplitError("join must be glue | magnet | dovetail | pin")
    if join != "glue" and not meshedit.have_boolean():
        raise SplitError("Magnet, dovetail and pin joins need manifold3d on the server.")
    if join == "magnet":
        return _add_magnet(below, above, origin, normal, p)
    if join == "pin":
        return _add_pin(below, above, origin, normal, p)
    if join == "dovetail":
        return _add_dovetail(below, above, origin, normal, p)
    return _add_glue_marks(below, above, origin, normal, p)


def _cut_list(mesh: trimesh.Trimesh, cuts: list[dict], join: str, p: dict) -> tuple[list[trimesh.Trimesh], list[dict]]:
    """Apply cuts in order. Each cut splits every current piece it intersects; join features added per cut."""
    parts = [mesh]
    join_reports = []
    for c in cuts:
        axis, pos = c["axis"], float(c["position"])
        nxt = []
        for part in parts:
            lo, hi = part.bounds
            i = _axis_i(axis)
            if not (lo[i] + 0.5 < pos < hi[i] - 0.5):
                nxt.append(part)
                continue
            below, above, normal = _slice_one(part, axis, pos)
            origin = normal * pos
            detail = {}
            if join:
                try:
                    below, above, detail = apply_join(below, above, origin, normal, join, p)
                except meshedit.OpError as e:
                    # Fall back to plain cut rather than failing the whole split
                    detail = {"join_warning": str(e)}
            join_reports.append({"axis": axis, "position": round(pos, 2), "join": join, **detail})
            nxt.extend([below, above])
        parts = nxt
        if len(parts) > MAX_PARTS:
            raise SplitError(f"Split would make more than {MAX_PARTS} pieces. Scale the model down, or cut fewer times.")
    return parts, join_reports


def smart_split(mesh: trimesh.Trimesh, p: dict) -> tuple[trimesh.Trimesh, dict]:
    """Auto or manual Smart Split. Returns parts arranged on one plate + an honest Simulated report."""
    join = (p.get("join") or "glue").lower()
    if join not in JOIN_KINDS:
        raise SplitError("join must be glue | magnet | dovetail | pin")
    mode = (p.get("mode") or "auto").lower()
    if mode not in ("auto", "manual"):
        raise SplitError("mode must be auto | manual")

    pid, bed, printer_name = bed_for(p.get("printer_id"))
    size = [float(v) for v in mesh.extents]

    if mode == "manual":
        axis = p.get("axis", "z")
        pos = meshedit._num(p, "position", None)
        cuts = [{"axis": axis, "position": pos}]
        if fits_bed(size, bed) and not p.get("force"):
            # Still allow a manual cut even when it already fits
            pass
    else:
        if fits_bed(size, bed):
            return mesh.copy(), {
                "message": f"Already fits the {printer_name} bed ({bed[0]:g} × {bed[1]:g} × {bed[2]:g} mm). No cut needed.",
                "parts": 1, "cuts": 0, "join": join, "printer_id": pid, "printer": printer_name,
                "bed_mm": list(bed), "size_mm": [round(v, 1) for v in size],
                "verification": SIMULATED, "fits_each": True,
            }
        plan = plan_cuts(size, bed)
        if not plan:
            raise SplitError("Could not plan cuts for this bed. Try a manual cut plane.")
        cuts = absolute_cuts(mesh, plan)

    gap = meshedit._num(p, "gap", GAP_MM, 0, 50)
    parts, join_reports = _cut_list(mesh, cuts, join, p)

    # Drop each part so the cut/largest face can sit on the bed — use existing lay_flat when helpful
    laid = []
    for part in parts:
        q = part.copy()
        lo, hi = q.bounds
        q.apply_translation([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])
        laid.append(q)

    combined, plate = orient.arrange(laid, (bed[0], bed[1]), gap, bed[2])
    # record where each piece came from, so Smart merge can put them back along the cuts later
    exact = plate.pop("_exact", None) or []
    pieces = []
    for part, xy in zip(parts, exact):
        lo, hi = part.bounds
        mv = np.array([xy[0] - lo[0], xy[1] - lo[1], -lo[2]])
        pieces.append({"at": [round(float(v), 4) for v in (lo + hi) / 2 + mv], "move": [round(float(v), 4) for v in mv]})
    each_fit = all(fits_bed(p.extents, bed) for p in laid)
    too = plate.get("too_big_parts") or []
    msg = (f"Smart Split: {len(parts)} piece(s) for {printer_name} "
           f"({bed[0]:g} × {bed[1]:g} mm) · join={join} · {SIMULATED}")
    if not each_fit:
        msg += f" · {len(too)} piece(s) still bigger than the bed — scale down or cut again"
    note = ("Connector and cut fit is Simulated until you test-print. "
            "Print a small fit coupon before a big model. "
            "Starting sizes come from ZEIM's split specs (magnet/dovetail/pin).")
    return combined, {
        "message": msg, "note": note, "parts": len(parts), "cuts": len(cuts),
        "cut_list": [{"axis": c["axis"], "position": round(float(c["position"]), 2)} for c in cuts],
        "joins": join_reports, "join": join, "mode": mode,
        "printer_id": pid, "printer": printer_name, "bed_mm": list(bed),
        "size_mm": [round(v, 1) for v in size],
        "plate": plate, "fits_each": each_fit, "verification": SIMULATED,
        "watertight": bool(combined.is_watertight),
        "_persist": {"pieces": pieces},
    }


def op_smart_split(m, p):
    return smart_split(m, p)
