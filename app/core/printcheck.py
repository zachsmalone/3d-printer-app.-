"""Print-aware checks in one place: does it fit the bed, how much overhang, how thin, and fit tolerances for holes/pegs.

Read-only and approximate: nothing here changes the mesh. Tolerances are conservative starting points, not measured
values for any specific printer; test a small print before relying on a fit.
"""
from __future__ import annotations

import itertools

import numpy as np
import trimesh

from . import orient, thickness

# extra clearance (mm) added to a hole's diameter / subtracted from a peg's, per process and fit. Starting points only.
TOLERANCE_MM = {
    "fdm":   {"tight": 0.15, "normal": 0.25, "loose": 0.40},
    "resin": {"tight": 0.05, "normal": 0.10, "loose": 0.20},
}
MIN_WALL_MM = {"fdm": 0.8, "resin": 0.5}


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


def run(m: trimesh.Trimesh, bed, process: str = "fdm", min_wall: float | None = None) -> dict:
    if process not in MIN_WALL_MM:
        raise ValueError("process must be fdm | resin")
    wall = MIN_WALL_MM[process] if min_wall is None else float(min_wall)
    ov = orient.overhang(m) if len(m.faces) else {}
    from . import guard
    try:
        th = guard.run(thickness.analyze, m, wall, mem_mb=1200, timeout=60)
    except (guard.Tripped, guard.Busy):
        th = {"min_wall_mm": wall, "ok": False, "reason": "Thickness check skipped: it needed more memory or time than allowed. Simplify first."}
    bedfit = fits_bed(m, tuple(bed))
    issues = []
    if not bedfit["fits_any_axis_orientation"]:
        issues.append("Too big for the build volume in every axis orientation; use Smart Split.")
    elif not bedfit["fits_as_is"]:
        issues.append("Fits the build volume only if turned; use Best position or rotate it.")
    if th.get("ok") and th["verdict"] != "ok":
        issues.append(f"Thin walls: {th['thin_count']} sampled spot(s) under {wall:g} mm (thinnest {th['min_found_mm']:g} mm).")
    if not th.get("ok"):
        issues.append(th.get("reason", "Thickness could not be checked."))
    if ov and ov["overhang_mm2"] > 0:
        issues.append(f"{ov['overhang_mm2']:.0f} mm² of steep overhang (past 45°) will probably need supports.")
    return {"process": process, "approximate": True, "ok": not issues, "issues": issues,
            "bed": bedfit, "overhang": {k: round(v, 2) for k, v in ov.items()}, "thickness": th}
