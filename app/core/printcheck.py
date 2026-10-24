"""Print-aware checks in one place: does it fit the bed, how much overhang, how thin, and fit tolerances for holes/pegs.

Read-only and approximate: nothing here changes the mesh. Tolerances are conservative starting points, not measured
values for any specific printer; test a small print before relying on a fit.

Edit upgrade 2: colour problem highlights (face categories + sample points).
Edit upgrade 5: checklist with one-tap fix actions (op + params the UI can run).
"""
from __future__ import annotations

import itertools
import math

import numpy as np
import trimesh

from . import orient, thickness

# extra clearance (mm) added to a hole's diameter / subtracted from a peg's, per process and fit. Starting points only.
TOLERANCE_MM = {
    "fdm":   {"tight": 0.15, "normal": 0.25, "loose": 0.40},
    "resin": {"tight": 0.05, "normal": 0.10, "loose": 0.20},
}
MIN_WALL_MM = {"fdm": 0.8, "resin": 0.5}

# UI colours (RGB 0-1) for problem categories on the model
HIGHLIGHT_COLORS = {
    "overhang": (1.0, 0.55, 0.1),   # orange
    "thin": (1.0, 0.2, 0.35),      # red/pink
    "ok": (0.56, 0.69, 0.88),      # default blue-ish
}


def tolerance(process: str, fit: str, nominal: float, kind: str = "hole") -> dict:
    if process not in TOLERANCE_MM or fit not in TOLERANCE_MM[process]:
        raise ValueError("process must be fdm | resin and fit must be tight | normal | loose")
    if kind not in ("hole", "peg"):
        raise ValueError("kind must be hole | peg")
    nominal = float(nominal)
    if not np.isfinite(nominal) or not 0.1 <= nominal <= 1000:
        raise ValueError("nominal size must be between 0.1 and 1000 mm")
    c = TOLERANCE_MM[process][fit]
    return {"nominal_mm": nominal, "clearance_mm": c, "adjusted_mm": round(nominal + c if kind == "hole" else nominal - c, 3),
            "kind": kind, "approximate": True, "note": "A conservative starting point, not measured for your printer; print a test first."}


def fits_bed(m: trimesh.Trimesh, bed: tuple[float, float, float]) -> dict:
    """Does the model fit the build volume in ANY of the 6 axis-aligned orientations (rotations about z allowed by swapping x/y)?"""
    ext = [float(x) for x in m.extents]
    bx, by, bz = (float(x) for x in bed)
    best = None
    for perm in itertools.permutations(range(3)):
        e = [ext[i] for i in perm]
        over = [max(0.0, e[0] - bx), max(0.0, e[1] - by), max(0.0, e[2] - bz)]
        score = sum(over)
        if best is None or score < best[0]:
            best = (score, perm, over)
    score, perm, over = best
    return {"fits_as_is": ext[0] <= bx and ext[1] <= by and ext[2] <= bz, "fits_any_axis_orientation": score == 0,
            "size_mm": [round(x, 2) for x in ext], "bed_mm": [bx, by, bz],
            "overhang_past_bed_mm": [round(x, 2) for x in over], "suggest_split": score > 0,
            "best_axes": [["x", "y", "z"][i] for i in perm]}


def _overhang_faces(m: trimesh.Trimesh) -> np.ndarray:
    """Boolean mask of faces that are steep downward overhangs (same rule as orient.overhang)."""
    if not len(m.faces):
        return np.zeros(0, bool)
    n = m.face_normals
    zmin = m.bounds[0][2]
    cz = m.triangles_center[:, 2] - zmin
    lim = -math.cos(math.radians(90 - orient.OVERHANG_DEG))
    return (n[:, 2] < lim) & (cz > orient.BED_EPS)


def _face_categories(m: trimesh.Trimesh, thin_face_ids: set[int] | None = None) -> list[str]:
    """Per-face category: overhang | thin | ok. thin wins over overhang when both apply."""
    n = len(m.faces)
    if n == 0:
        return []
    over = _overhang_faces(m)
    cats = ["ok"] * n
    for i in np.nonzero(over)[0]:
        cats[int(i)] = "overhang"
    if thin_face_ids:
        for i in thin_face_ids:
            if 0 <= i < n:
                cats[i] = "thin"
    return cats


def _thin_face_ids_from_points(m: trimesh.Trimesh, thin_points: list[dict]) -> set[int]:
    """Map thin sample points to nearest face indices (for colouring)."""
    ids: set[int] = set()
    if not thin_points or not len(m.faces):
        return ids
    pts = np.array([p["at"] for p in thin_points if p.get("at")], float)
    if not len(pts):
        return ids
    try:
        # closest face via proximity
        q = trimesh.proximity.ProximityQuery(m)
        _, _, fid = q.on_surface(pts)
        for i in fid:
            ids.add(int(i))
    except Exception:
        # fallback: nearest triangle centre
        ctr = m.triangles_center
        for pt in pts:
            d = np.linalg.norm(ctr - pt, axis=1)
            ids.add(int(np.argmin(d)))
    return ids


def _fixes(issues_meta: list[dict], bedfit: dict, process: str) -> list[dict]:
    """One-tap fix actions the Edit UI can POST as /op or call directly."""
    fixes = []
    for meta in issues_meta:
        code = meta.get("code")
        if code == "too_big":
            fixes.append({
                "id": "smart_split",
                "label": "Smart Split to fit bed",
                "op": "smart_split",
                "params": {"mode": "auto", "join": "glue", "gap": 5},
                "issue": meta.get("text"),
            })
        elif code == "needs_rotate":
            fixes.append({
                "id": "best_orient",
                "label": "Best position (least overhang)",
                "op": "best_orient",
                "params": {},
                "issue": meta.get("text"),
            })
            fixes.append({
                "id": "lay_flat",
                "label": "Lay flat",
                "op": "lay_flat",
                "params": {},
                "issue": meta.get("text"),
            })
        elif code == "thin_walls":
            fixes.append({
                "id": "scale_up_thin",
                "label": "Scale up 10% (thicker walls)",
                "op": "scale",
                "params": {"factor": 1.1, "pivot": "base"},
                "issue": meta.get("text"),
            })
        elif code == "inverted":
            fixes.append({
                "id": "repair",
                "label": "Fix / repair (flip normals)",
                "op": "repair",
                "params": {"fix_normals": True, "fill_holes": True, "remove_duplicates": True},
                "issue": meta.get("text"),
            })
        elif code == "overhang":
            fixes.append({
                "id": "best_orient_oh",
                "label": "Best position to reduce overhang",
                "op": "best_orient",
                "params": {},
                "issue": meta.get("text"),
            })
            fixes.append({
                "id": "paint_supports",
                "label": "Open paint-on supports in Slicer",
                "action": "open_slicer_paint",
                "issue": meta.get("text"),
            })
    # de-dupe by id
    seen, out = set(), []
    for f in fixes:
        if f["id"] in seen:
            continue
        seen.add(f["id"]); out.append(f)
    return out


def run(m: trimesh.Trimesh, bed, process: str = "fdm", min_wall: float | None = None) -> dict:
    if process not in MIN_WALL_MM:
        raise ValueError("process must be fdm | resin")
    wall = MIN_WALL_MM[process] if min_wall is None else float(min_wall)
    ov = orient.overhang(m) if len(m.faces) else {}
    from . import guard
    try:
        th = guard.run(thickness.analyze, m, wall, mem_mb=1200, timeout=60)
    except (guard.Tripped, guard.Busy, MemoryError, OSError):
        th = {"ok": False, "reason": "Thickness check skipped: it needed more memory or time than allowed. Simplify first.",
              "min_wall_mm": wall, "thin_points": []}
    bedfit = fits_bed(m, tuple(bed))
    issues = []
    issues_meta = []
    if not bedfit["fits_any_axis_orientation"]:
        text = "Too big for the build volume in every axis orientation; use Smart Split."
        issues.append(text); issues_meta.append({"code": "too_big", "text": text})
    elif not bedfit["fits_as_is"]:
        text = "Fits the build volume only if turned; use Best position or rotate it."
        issues.append(text); issues_meta.append({"code": "needs_rotate", "text": text})
    if th.get("ok") and th.get("verdict") != "ok":
        text = f"Thin walls: {th['thin_count']} sampled spot(s) under {wall:g} mm (thinnest {th['min_found_mm']:g} mm)."
        issues.append(text); issues_meta.append({"code": "thin_walls", "text": text})
    if not th.get("ok"):
        text = th.get("reason", "Thickness could not be checked.")
        issues.append(text); issues_meta.append({"code": "thickness_skip", "text": text})
    if len(m.faces) and m.is_watertight and float(m.volume) < 0:
        text = "The model looks inside out (normals flipped); slicers may print it wrong. Run Fix to flip it, or dismiss and continue."
        issues.append(text); issues_meta.append({"code": "inverted", "text": text})
    if ov and ov["overhang_mm2"] > 0:
        text = f"{ov['overhang_mm2']:.0f} mm² of steep overhang (past 45°) will probably need supports."
        issues.append(text); issues_meta.append({"code": "overhang", "text": text})

    thin_pts = th.get("thin_points") or []
    thin_ids = _thin_face_ids_from_points(m, thin_pts) if th.get("ok") else set()
    # Cap face category payload for huge meshes: send only non-ok face indices
    cats = _face_categories(m, thin_ids)
    highlights = []
    for i, c in enumerate(cats):
        if c != "ok":
            highlights.append({"face": i, "category": c})
        if len(highlights) >= 50_000:  # safety cap
            break

    return {
        "process": process, "approximate": True, "ok": not issues, "issues": issues,
        "issues_meta": issues_meta,
        "fixes": _fixes(issues_meta, bedfit, process),
        "bed": bedfit,
        "overhang": {k: round(v, 2) for k, v in ov.items()},
        "thickness": th,
        "highlights": {
            "faces": highlights,
            "thin_points": thin_pts,
            "colors": {k: list(v) for k, v in HIGHLIGHT_COLORS.items()},
            "face_count": len(m.faces),
            "note": "Colours mark overhang (orange) and thin spots (red). Approximate — sample-based.",
        },
    }
