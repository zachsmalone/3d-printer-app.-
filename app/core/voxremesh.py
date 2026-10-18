"""Voxel remesh (the Nomad-class enabler, applied to ZEIM's job: one-click watertight repair).

Voxelize the mesh at a chosen pitch and rebuild it with marching cubes: a fresh, uniform,
watertight triangulation — the standard 'make it printable' fallback for meshes that are
broken beyond targeted repair (self-intersections, holes, non-manifold edges). Original
code; the voxel/marching-cubes conventions are public.
"""
from __future__ import annotations

import numpy as np
import trimesh

MIN_PITCH = 0.05      # mm per voxel — a 0.05 mm grid on a 100 mm part is 2000³ voxels: refused below
MAX_PITCH = 10.0


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


def op_voxremesh(m: trimesh.Trimesh, p: dict) -> tuple[trimesh.Trimesh, dict]:
    from .meshedit import OpError, _check      # late import: meshedit owns the OPS table
    """Replace the mesh with a marching-cubes rebuild of its voxelization. Detail below the
    pitch is lost (that is the point: a clean, uniform, watertight mesh), and the volume is
    approximately preserved — the report says by how much."""
    pitch = _pitch(m, p)
    # a BROKEN mesh has no meaningful volume — the drift check only applies when the input
    # was watertight (the whole point of this op is fixing meshes whose volume is undefined)
    solid_in = bool(m.is_watertight) and len(m.faces) > 0
    before = float(abs(m.volume)) if solid_in else 0.0
    try:
        grid = m.voxelized(pitch=pitch)
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
        raise OpError(f"the voxel remesh changed the volume by {drift:.0%} — the pitch is too coarse for this model.")
    rep = {"pitch_mm": pitch, "triangles_before": int(len(m.faces)), "triangles_after": int(len(out.faces)),
           "volume_drift": drift, "watertight": True,
           "message": f"Voxel remesh at {pitch:.2f} mm ({len(out.faces)} triangles, watertight)"}
    return _check(out), rep
