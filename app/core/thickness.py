"""Print-aware check: where is the model thinner than the printer can make?

Samples points on the surface and shoots a ray straight into the material; the distance to the far side is the local
thickness. HONEST LIMITS: it is a sampled estimate (thin spots between samples can be missed), it measures straight-through
thickness (not the minimum feature width in-plane), and it needs a mesh that is closed enough for rays to behave.
Read-only: it never changes the mesh.
"""
from __future__ import annotations

import numpy as np
import trimesh

MAX_FACES = 150_000
SAMPLES_MAX = 5000


RAY_CHUNK = 250     # rays per batch: trimesh's pure-numpy ray engine needs ~1.3 GB for 2000 rays at once on a
                    # 20k-face mesh, ~0.27 GB in batches of 250 (same hits, same speed). Keeps guarded children small (N3).


def first_hits(m: trimesh.Trimesh, origins: np.ndarray, directions: np.ndarray, chunk: int = RAY_CHUNK):
    """m.ray.intersects_location(..., multiple_hits=False) in batches. Returns (locations, ray_index)."""
    locs, idx = [], []
    for s in range(0, len(origins), chunk):
        loc, ir, _ = m.ray.intersects_location(origins[s:s + chunk], directions[s:s + chunk], multiple_hits=False)
        locs.append(np.asarray(loc, float).reshape(-1, 3)); idx.append(np.asarray(ir, int) + s)
    if not locs:
        return np.zeros((0, 3)), np.zeros(0, int)
    return np.concatenate(locs), np.concatenate(idx)


OPPOSITE_MAX_DEG = 18.0   # QA (Kobi): a thin spot needs a nearly parallel opposite face on the SAME shell
MIN_THIN_SPOTS = 2        # and at least this many such spots before anything is called thin


def first_hits_faces(m: trimesh.Trimesh, origins: np.ndarray, directions: np.ndarray, chunk: int = RAY_CHUNK):
    """Like first_hits, plus the index of the triangle each ray hit."""
    locs, idx, tri = [], [], []
    for s in range(0, len(origins), chunk):
        loc, ir, it = m.ray.intersects_location(origins[s:s + chunk], directions[s:s + chunk], multiple_hits=False)
        locs.append(np.asarray(loc, float).reshape(-1, 3)); idx.append(np.asarray(ir, int) + s); tri.append(np.asarray(it, int))
    if not locs:
        return np.zeros((0, 3)), np.zeros(0, int), np.zeros(0, int)
    return np.concatenate(locs), np.concatenate(idx), np.concatenate(tri)


def shell_ids(m: trimesh.Trimesh) -> np.ndarray:
    """Connected-component (shell) id of every face."""
    lab = np.zeros(len(m.faces), int)
    try:
        for k, comp in enumerate(trimesh.graph.connected_components(m.face_adjacency, nodes=np.arange(len(m.faces)))):
            lab[np.asarray(comp, int)] = k
    except Exception:
        pass
    return lab


def real_thin(m: trimesh.Trimesh, src_faces: np.ndarray, hit_faces: np.ndarray, d: np.ndarray, min_mm: float,
              shells: np.ndarray | None = None) -> np.ndarray:
    """Mask of measurements that are genuinely thin walls: under min_mm, the ray hit the SAME shell, and the face it hit
    faces back within OPPOSITE_MAX_DEG of exactly opposite. Clears false alarms from star tips, debossed-text slivers
    (rays grazing a sharp corner) and overlapping shells, while real fins / thin walls (parallel faces) still count."""
    if shells is None:
        shells = shell_ids(m)
    n0, n1 = m.face_normals[src_faces], m.face_normals[hit_faces]
    opposite = np.einsum("ij,ij->i", n0, n1) <= -np.cos(np.radians(OPPOSITE_MAX_DEG))
    return (d < min_mm) & (shells[src_faces] == shells[hit_faces]) & opposite


def analyze(m: trimesh.Trimesh, min_wall: float = 0.8, samples: int = 2000) -> dict:
    min_wall = float(min_wall)
    if not (0.05 <= min_wall <= 50):
        raise ValueError("min_wall must be between 0.05 and 50 mm")
    samples = int(max(100, min(samples, SAMPLES_MAX)))
    base = {"min_wall_mm": min_wall, "approximate": True,
            "note": "Sampled estimate of straight-through thickness; thin spots between samples can be missed."}
    if len(m.faces) == 0:
        return {**base, "ok": False, "reason": "The model has no triangles to analyse."}
    if len(m.faces) > MAX_FACES:
        return {**base, "ok": False, "skipped": "too_detailed",
                "reason": f"The model is too large to analyse fully ({len(m.faces):,} triangles; the thickness check "
                          f"handles up to {MAX_FACES:,}). Simplify a copy first for a full check."}
    if not m.is_watertight:
        return {**base, "ok": False, "reason": "The model has holes; run Fix first so thickness can be measured."}
    pts, fi = trimesh.sample.sample_surface(m, samples, seed=1)
    nn = m.face_normals[fi]
    org = pts - nn * 1e-3                                    # nudge inside so the ray does not hit its own start face
    loc, ir, hit = first_hits_faces(m, org, -nn)
    if not len(ir):
        return {**base, "ok": False, "reason": "Could not measure thickness on this model."}
    d = np.linalg.norm(loc - org[ir], axis=1)
    thin = real_thin(m, fi[ir], hit, d, min_wall)
    if thin.sum() < MIN_THIN_SPOTS:
        thin[:] = False
    d = np.where(thin | (d >= min_wall), d, min_wall)        # filtered-out readings are not reported as the thinnest
    worst = np.argsort(d)[:10]
    return {**base, "ok": True, "samples_measured": int(len(d)), "min_found_mm": round(float(d.min()), 3),
            "thin_fraction": round(float(thin.mean()), 4), "thin_count": int(thin.sum()),
            "thin_points": [{"at": [round(float(x), 3) for x in pts[ir][i]], "thickness_mm": round(float(d[i]), 3)} for i in worst if d[i] < min_wall],
            "verdict": "ok" if not thin.any() else ("some thin spots" if thin.mean() < 0.05 else "mostly too thin")}
