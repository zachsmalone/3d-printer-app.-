"""Voxel remesh (the Nomad-class enabler, applied to ZEIM's job: one-click watertight repair).

Voxelize the mesh at a chosen pitch and rebuild it with marching cubes: a fresh, uniform,
watertight triangulation — the standard 'make it printable' fallback for meshes that are
broken beyond targeted repair (self-intersections, holes, non-manifold edges). Original
code; the voxel/marching-cubes conventions are public.

Honest limits, disclosed up front: detail below the pitch is LOST (that is the point), the
surface gains about half a voxel of padding, and ENCLOSED INTERNAL CAVITIES are filled —
a hollow sphere becomes a solid. Through-holes (a tube's bore) are open at the ends and
survive; an intended sealed cavity does not.
"""
from __future__ import annotations

import numpy as np
import trimesh

MIN_PITCH = 0.05      # mm per voxel — a 0.05 mm grid on a 100 mm part is 2000³ voxels: refused below
MAX_PITCH = 10.0
MAX_CELLS = 8_000_000   # 200³ — the voxel grid's memory budget, checked BEFORE any allocation


def _pitch(m: trimesh.Trimesh, p: dict) -> float:
    from .meshedit import OpError               # late import: meshedit owns the OPS table
    if p.get("pitch") is not None:
        try:
            v = float(p["pitch"])
        except (TypeError, ValueError):
            raise OpError("pitch must be a number (mm per voxel).")
        if not MIN_PITCH <= v <= MAX_PITCH:
            raise OpError(f"pitch must be {MIN_PITCH}..{MAX_PITCH} mm per voxel.")
        return v
    # default: ~96 voxels across the largest dimension, clamped
    ext = float(np.max(m.extents)) if len(m.faces) else 0.0
    if ext <= 0:
        raise OpError("the model is empty.")
    return float(np.clip(ext / 96.0, MIN_PITCH, MAX_PITCH))


def _budget(m: trimesh.Trimesh, pitch: float) -> None:
    """The grid is extents/pitch per axis — but the voxelizer PADS: a CONSERVATIVE UPPER
    BOUND on the real grid is ceil(ext/pitch) + 2 cells per axis (measured on trimesh
    5.1.1: a 100 mm axis at pitch 1 is 101 cells; at pitch 3.7 it is 29 — inside the
    bound). Budget that bound, not the raw ratio — a pitch RANGE is not a resource bound:
    100 mm at 0.05 mm is ~8 billion cells. Refuse before voxelization ever runs."""
    from .meshedit import OpError
    ext = np.asarray(m.extents, dtype=float)
    cells = float(np.prod(np.ceil(ext / pitch) + 2))
    if cells > MAX_CELLS:
        raise OpError(
            f"voxel remesh needs ~{cells / 1e6:.0f} million cells at that pitch (budget "
            f"{MAX_CELLS // 1_000_000} M) — use a coarser pitch or a smaller model.")


def op_voxremesh(m: trimesh.Trimesh, p: dict) -> tuple[trimesh.Trimesh, dict]:
    from .meshedit import OpError, _check      # late import: meshedit owns the OPS table
    """Replace the mesh with a marching-cubes rebuild of its voxelization. Detail below the
    pitch is lost (that is the point: a clean, uniform, watertight mesh), and the volume is
    approximately preserved — the report says by how much."""
    pitch = _pitch(m, p)
    _budget(m, pitch)                      # resource bound BEFORE voxelization
    # Repair pass first: close simple holes BEFORE voxelizing — a voxelization of an OPEN
    # surface cannot tell interior from exterior through the gap, and marching cubes then
    # yields a closed THIN SHELL (watertight but hollow — useless to print). fill_holes()
    # closes triangle/quad holes; big irregular tears may survive it.
    work = m
    try:
        work = m.copy()
        work.fill_holes()
    except Exception:
        work = m
    # a BROKEN mesh has no meaningful volume — the drift check only applies when the input
    # (after the repair pass) is watertight, which is also when the voxel fill can work
    solid_in = bool(work.is_watertight) and len(work.faces) > 0
    before = float(abs(work.volume)) if solid_in else 0.0
    try:
        grid = work.voxelized(pitch=pitch)   # the REPAIRED mesh: interior vs exterior is well-defined
        grid.fill()                          # surface voxels -> solid: a single clean wall
        out = grid.marching_cubes            # built in VOXEL units...
        out.apply_transform(grid.transform)  # ...so apply the grid's world transform (mm + origin)
    except OpError:
        raise
    except Exception as e:
        raise OpError(f"voxel remesh failed: {e}")
    if out is None or len(out.faces) == 0:
        raise OpError("the voxel remesh came out empty — try a smaller pitch.")
    after = float(abs(out.volume))
    drift = abs(after - before) / before if solid_in and before > 0 else None
    if drift is not None and drift > 0.5:
        if after > before:
            # the volume GREW: growth alone does not PROVE a sealed cavity (coarse pitch and
            # voxel padding grow solids too), so say what is known: it MIGHT be a filled
            # cavity. Refuse rather than silently change the geometry by that much.
            raise OpError(
                f"the volume would grow by +{drift:.0%} — a sealed internal cavity may have "
                f"been filled (or the pitch is simply too coarse for this model); refused "
                f"rather than silently change it. (Through-holes survive; sealed cavities "
                f"are always filled by this op.)")
        raise OpError(f"the voxel remesh changed the volume by {drift:.0%} — the pitch is too coarse for this model.")
    note = ""
    if drift is not None and after > before * 1.02:
        # ANY meaningful growth is disclosed, with the honest ambiguity: it may be padding,
        # coarse pitch, or a filled sealed cavity (sealed cavities are ALWAYS filled).
        note = f" (volume +{drift:.0%}: voxel padding, coarse pitch, or a filled sealed cavity)"
    rep = {"pitch_mm": pitch, "triangles_before": int(len(m.faces)), "triangles_after": int(len(out.faces)),
           "volume_drift": drift, "watertight": True,
           "holes_closed": bool(not m.is_watertight and work.is_watertight),
           "shell_risk": not solid_in,      # input stayed open: the result may be a hollow shell
           "message": f"Voxel remesh at {pitch:.2f} mm ({len(out.faces)} triangles, watertight){note}"}
    return _check(out), rep
