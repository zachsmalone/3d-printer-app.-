"""2D->3D: turn the engine's raw mesh into a printable figure or bust.

Steps: keep the main body (drop floating specks), stand it on the bed, cut a flat bottom so it does not tip,
scale to the chosen height, then the same auto-repair Smart Fix uses (stlrepair.repair_mesh). A light Taubin
smooth takes grain off the surface and is reverted if it would change the outer size. A very dense mesh is
decimated with meshedit.op_simplify. If it is still not watertight, a voxel remesh closes it. Every step is
reported; nothing here blocks a result.
"""
from __future__ import annotations

import io

import numpy as np
import trimesh

from . import geometry, meshthumb, meshedit, stlrepair, voxremesh

MODES = {"figure": {"height_mm": 80.0, "flat": 0.02, "label": "Figure"},
         "bust": {"height_mm": 60.0, "flat": 0.04, "label": "Bust"}}
MIN_H, MAX_H = 20.0, 250.0
# Only very dense TripoSR meshes are reduced. The target stays high enough to keep a face.
DECIMATE_OVER = 90_000
DECIMATE_TARGET = 60_000
# Taubin pair: a short positive step, then a slightly stronger negative step, so the shape does not shrink away.
_SMOOTH_LAM = 0.45
_SMOOTH_MU = -0.48
_SMOOTH_ITERS = 2


class MeshError(ValueError):
    pass


def _taubin(v: np.ndarray, faces: np.ndarray, iterations: int = _SMOOTH_ITERS, lam: float = _SMOOTH_LAM, mu: float = _SMOOTH_MU) -> np.ndarray:
    """Two-step Taubin smooth. Low-frequency shape stays; grain moves a little. Topology is unchanged."""
    faces = np.asarray(faces, np.int64)
    if len(faces) == 0 or len(v) == 0:
        return np.asarray(v, np.float64)
    src = np.concatenate([faces[:, 0], faces[:, 1], faces[:, 2], faces[:, 1], faces[:, 2], faces[:, 0]])
    dst = np.concatenate([faces[:, 1], faces[:, 2], faces[:, 0], faces[:, 0], faces[:, 1], faces[:, 2]])
    order = np.lexsort((dst, src))
    src, dst = src[order], dst[order]
    keep = np.empty(len(src), dtype=bool)
    keep[0] = True
    keep[1:] = (src[1:] != src[:-1]) | (dst[1:] != dst[:-1])
    src, dst = src[keep], dst[keep]
    deg = np.bincount(src, minlength=len(v)).astype(np.float64)
    deg[deg == 0] = 1.0
    out = np.asarray(v, np.float64).copy()
    for _ in range(iterations):
        for step in (lam, mu):
            acc = np.zeros_like(out)
            np.add.at(acc, src, out[dst])
            out = out + step * ((acc / deg[:, None]) - out)
    return out


def light_smooth(mesh: trimesh.Trimesh, height_mm: float) -> tuple[trimesh.Trimesh, str]:
    """Grain off the surface. Revert if the outer size or the volume would move more than a little."""
    if len(mesh.faces) < 50:
        return mesh, ""
    v0 = np.asarray(mesh.vertices, np.float64)
    ext0 = np.asarray(mesh.extents, np.float64)
    watertight = bool(mesh.is_watertight)
    vol0 = abs(float(mesh.volume)) if watertight else 0.0
    moved = _taubin(v0, mesh.faces)
    out = mesh.copy()
    out.vertices = moved
    limit = 0.03 * max(float(height_mm), 1.0)
    if np.any(np.abs(np.asarray(out.extents, np.float64) - ext0) > limit):
        return mesh, "Smoothing skipped. It would have changed the outer size."
    if watertight and vol0 > 0 and out.is_watertight:
        vol1 = abs(float(out.volume))
        if abs(vol1 - vol0) / vol0 > 0.04:
            return mesh, "Smoothing skipped. It would have changed the volume."
    if float(np.linalg.norm(moved - v0, axis=1).mean()) < 1e-4:
        return mesh, ""
    return out, "Light smoothing to take the grain off the surface. The outer shape is kept."


def decimate_for_print(mesh: trimesh.Trimesh, *, over: int | None = None, target: int | None = None) -> tuple[trimesh.Trimesh, str]:
    """Reduce a very dense mesh with the same simplifier the editor uses. Leave a modest mesh alone."""
    over_n = DECIMATE_OVER if over is None else int(over)
    target_n = DECIMATE_TARGET if target is None else int(target)
    n = len(mesh.faces)
    if n <= over_n or n < 100:
        return mesh, ""
    if not meshedit.have_simplify():
        return mesh, "Triangle count left as it is. The simplifier is not installed."
    keep = float(np.clip(target_n / n, 0.05, 0.95))
    try:
        out, _rep = meshedit.op_simplify(mesh, {"keep_ratio": keep})
    except meshedit.OpError:
        return mesh, "Triangle count left as it is. Simplifying would have broken the surface."
    if len(out.faces) >= n:
        return mesh, ""
    return out, f"Triangle count {n:,} → {len(out.faces):,} for slicing. The overall shape is kept."


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
    closed = int((rep.get("fixed") or {}).get("hole_edges_closed") or 0)
    if closed:
        notes.append("Filled holes left in the mesh.")
    m, smooth_note = light_smooth(m, h)
    if smooth_note:
        notes.append(smooth_note)
    m, dec_note = decimate_for_print(m)
    if dec_note:
        notes.append(dec_note)
    if dec_note and not m.is_watertight:
        try:
            m, rep2 = stlrepair.repair_mesh(m)
            rep = rep2
        except Exception:
            pass
    if not m.is_watertight:
        try:
            m2, _ = voxremesh.op_voxremesh(m, {"pitch": max(h / 160.0, 0.2)})
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
