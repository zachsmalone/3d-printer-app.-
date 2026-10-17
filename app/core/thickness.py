"""Print-aware check: where is the model thinner than the printer can make?

Samples points on the surface and shoots a ray straight into the material; the distance to the far side is the local
thickness. HONEST LIMITS: it is a sampled estimate (thin spots between samples can be missed), it measures straight-through
thickness (not the minimum feature width in-plane), and it needs a mesh that is closed enough for rays to behave.
Read-only: it never changes the mesh.
"""
from __future__ import annotations

import numpy as np
import trimesh

MAX_FACES = 400_000
SAMPLES_MAX = 5000


def analyze(m: trimesh.Trimesh, min_wall: float = 0.8, samples: int = 2000) -> dict:
    min_wall = float(min_wall)
    if not (0.05 <= min_wall <= 50):
        raise ValueError("min_wall must be between 0.05 and 50 mm")
    samples = int(max(100, min(samples, SAMPLES_MAX)))
    base = {"min_wall_mm": min_wall, "approximate": True,
            "note": "Sampled estimate of straight-through thickness; thin spots between samples can be missed."}
    if len(m.faces) == 0 or len(m.faces) > MAX_FACES:
        return {**base, "ok": False, "reason": "No triangles, or too many to analyse; simplify first."}
    if not m.is_watertight:
        return {**base, "ok": False, "reason": "The model has holes; run Fix first so thickness can be measured."}
    pts, fi = trimesh.sample.sample_surface(m, samples, seed=1)
    nn = m.face_normals[fi]
    org = pts - nn * 1e-3                                    # nudge inside so the ray does not hit its own start face
    loc, ir, _ = m.ray.intersects_location(org, -nn, multiple_hits=False)
    if not len(ir):
        return {**base, "ok": False, "reason": "Could not measure thickness on this model."}
    d = np.linalg.norm(loc - org[ir], axis=1)
    thin = d < min_wall
    worst = np.argsort(d)[:10]
    return {**base, "ok": True, "samples_measured": int(len(d)), "min_found_mm": round(float(d.min()), 3),
            "thin_fraction": round(float(thin.mean()), 4), "thin_count": int(thin.sum()),
            "thin_points": [{"at": [round(float(x), 3) for x in pts[ir][i]], "thickness_mm": round(float(d[i]), 3)} for i in worst if d[i] < min_wall],
            "verdict": "ok" if not thin.any() else ("some thin spots" if thin.mean() < 0.05 else "mostly too thin")}
