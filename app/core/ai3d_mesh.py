"""2D->3D: turn the engine's raw mesh into a printable figure or bust.

Steps: keep the main body (drop floating specks), stand it on the bed, cut a flat bottom so it does not tip,
scale to the chosen height, then the same auto-repair Smart Fix uses (stlrepair.repair_mesh); if it is still not
watertight, a voxel remesh closes it. Every step is reported; nothing here blocks a result.
"""
from __future__ import annotations

import io

import numpy as np
import trimesh

from . import geometry, meshthumb, stlrepair

MODES = {"figure": {"height_mm": 80.0, "flat": 0.02, "label": "Figure"},
         "bust": {"height_mm": 60.0, "flat": 0.04, "label": "Bust"}}
MIN_H, MAX_H = 20.0, 250.0


class MeshError(ValueError):
    pass


def load(data: bytes) -> trimesh.Trimesh:
    try:
        m = trimesh.load(io.BytesIO(data), file_type="ply", force="mesh", process=False)
    except Exception:
        raise MeshError("The engine sent back something that is not a mesh.")
    if not isinstance(m, trimesh.Trimesh) or len(m.faces) == 0:
        raise MeshError("The engine could not find a shape in this photo. A plain background and good light help.")
    return m


def finish(raw: trimesh.Trimesh, mode: str, height_mm: float | None = None) -> tuple[geometry.Model, dict]:
    cfg = MODES.get(mode, MODES["figure"])
    h = float(np.clip(height_mm or cfg["height_mm"], MIN_H, MAX_H))
    notes = []
    m = trimesh.Trimesh(np.asarray(raw.vertices, float), np.asarray(raw.faces, np.int64), process=True)
    parts = m.split(only_watertight=False)
    if len(parts) > 1:
        big = max(parts, key=lambda p: p.area)
        keep = [p for p in parts if p.area >= 0.05 * big.area]
        if len(keep) < len(parts):
            notes.append(f"Removed {len(parts) - len(keep)} small loose piece(s).")
        m = trimesh.util.concatenate(keep)
    m.apply_translation(-m.bounds[0])
    z_cut = float(m.extents[2] * cfg["flat"])
    try:
        cut = trimesh.intersections.slice_mesh_plane(m, [0, 0, 1], [0, 0, z_cut], cap=True)
        if len(cut.faces):
            m = cut
            notes.append("Flat bottom added so it stands on the bed.")
    except Exception:
        notes.append("Could not cut a flat bottom; add a base or supports in your slicer.")
    m.apply_translation([-(m.bounds[0][0] + m.bounds[1][0]) / 2, -(m.bounds[0][1] + m.bounds[1][1]) / 2, -m.bounds[0][2]])
    m.apply_scale(h / max(float(m.extents[2]), 1e-6))
    try:
        m, rep = stlrepair.repair_mesh(m)
    except Exception as e:  # never block: keep the unrepaired mesh and say so
        rep = {"warnings": [f"Auto-repair could not run ({type(e).__name__})."], "after": {}}
    if not m.is_watertight:
        from .voxremesh import op_voxremesh
        try:
            m2, _ = op_voxremesh(m, {"pitch": max(h / 160.0, 0.2)})
            if m2.is_watertight:
                m = m2; notes.append("Closed remaining gaps with a voxel remesh (very fine detail may soften).")
        except Exception:
            pass
    if m.is_watertight and m.volume < 0:
        m.invert()
    v, f = np.asarray(m.vertices, float), np.asarray(m.faces, np.int64)
    thumb = meshthumb.render(v, f)
    model = geometry.Model(bodies=[geometry.Body(cfg["label"], v, f)], mode="ai3d",
                           info={"ai": True, "ai_engine": "TripoSR", "ai3d_mode": mode}, thumb=thumb, single=(v, f))
    warnings = list(rep.get("warnings", []))
    if not m.is_watertight:
        warnings.append("Not fully watertight. Most slicers still cope; Smart Fix can try again.")
    return model, {"height_mm": round(h, 1), "watertight": bool(m.is_watertight), "notes": notes,
                   "warnings": warnings, "repair": rep.get("fixed", {})}


def fake_engine_mesh(mode: str) -> bytes:
    """TEST DOUBLE (ZEIM_AI3D_FAKE=1 / tests): a made-up stacked shape, not AI output. Used only when no engine runs."""
    body = trimesh.creation.capsule(height=1.0, radius=0.45)
    head = trimesh.creation.icosphere(3, radius=0.42); head.apply_translation([0, 0, 1.25])
    parts = [head] if mode == "bust" else [body, head]
    if mode == "bust":
        sh = trimesh.creation.cylinder(radius=0.6, height=0.5); sh.apply_translation([0, 0, 0.7]); parts.append(sh)
    m = trimesh.util.concatenate(parts)
    return m.export(file_type="ply")
