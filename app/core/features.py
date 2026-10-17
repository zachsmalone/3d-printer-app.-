"""Detect flat faces, cylinders and holes in a triangle mesh so they can be picked like native features.

HONEST LIMIT: everything here is *mesh-derived and approximate* (angle/fit tolerances), not exact B-rep geometry.
Read-only: it never changes the mesh.
"""
from __future__ import annotations

import hashlib
from collections import OrderedDict

import numpy as np
import trimesh

MAX_FACES = 400_000          # skip analysis above this triangle count
MAX_REPORT = 200
MAX_IDS = 2000               # triangle ids returned per feature (others flagged via `ids_truncated`)
CACHE_MAX = 8             # planes/cylinders returned, biggest first
PLANE_TOL_DEG = 1.0
MIN_PLANE_AREA_FRAC = 1e-4   # ignore specks smaller than this share of the surface
CYL_RADIAL_TOL = 0.03        # max relative radius spread for a cylinder
MIN_CYL_TRIS = 12


def _round(v, n=4):
    return [round(float(x), n) for x in v]


def planar_faces(m: trimesh.Trimesh) -> list[dict]:
    """Groups of connected, (nearly) coplanar triangles."""
    adj = m.face_adjacency
    ang = m.face_adjacency_angles
    ok = ang < np.radians(PLANE_TOL_DEG)
    comps = trimesh.graph.connected_components(adj[ok], nodes=np.arange(len(m.faces)), min_len=1)
    total = float(m.area) or 1.0
    out = []
    for c in comps:
        area = float(m.area_faces[c].sum())
        if area < total * MIN_PLANE_AREA_FRAC:
            continue
        n = m.face_normals[c]
        w = m.area_faces[c][:, None]
        normal = (n * w).sum(0)
        normal /= (np.linalg.norm(normal) or 1.0)
        # chains of tiny angles on a smooth curved surface must NOT count as flat: every triangle has to stay near the mean plane
        if (n @ normal).min() < np.cos(np.radians(2 * PLANE_TOL_DEG)):
            continue
        centroid = (m.triangles_center[c] * w).sum(0) / w.sum()
        spread = np.abs((m.triangles_center[c] - centroid) @ normal)
        if spread.max() > 0.01 * max(float(np.ptp(m.bounds, axis=0).max()), 1e-9):
            continue
        out.append({"kind": "plane", "faces": len(c), "area": round(area, 3), "normal": _round(normal),
                    "origin": _round(centroid), "face_ids": [int(i) for i in c[:MAX_IDS]], "ids_truncated": len(c) > MAX_IDS, "approximate": True})
    out.sort(key=lambda d: -d["area"])
    return out


def cylinders(m: trimesh.Trimesh, planes: list[dict]) -> list[dict]:
    """Curved patches whose triangle normals are all perpendicular to one axis and sit at one radius from it."""
    plane_ids = set()
    for p in planes:
        plane_ids.update(p["face_ids"])
    adj = m.face_adjacency
    ang = m.face_adjacency_angles
    smooth = ang < np.radians(40)          # coplanar triangle pairs (a flat strip of the barrel) must stay connected
    comps = trimesh.graph.connected_components(adj[smooth], nodes=np.arange(len(m.faces)), min_len=MIN_CYL_TRIS)
    out = []
    for c in comps:
        n = m.face_normals[c]
        # axis = direction least explained by the normals (smallest singular vector)
        _, s, vt = np.linalg.svd(n - 0, full_matrices=False)
        axis = vt[-1]
        if s[1] < 0.15 * s[0] or np.abs(n @ axis).max() > 0.08:       # needs normals fanning round an axis, not one flat patch
            continue
        pts = m.triangles_center[c]
        mean = pts.mean(0)
        a = np.cross(axis, [1, 0, 0]) if abs(axis[0]) < 0.9 else np.cross(axis, [0, 1, 0])
        a /= np.linalg.norm(a)
        b = np.cross(axis, a)
        xy = np.c_[(pts - mean) @ a, (pts - mean) @ b]
        A = np.c_[2 * xy, np.ones(len(xy))]
        sol, *_ = np.linalg.lstsq(A, (xy ** 2).sum(1), rcond=None)
        cx, cy = sol[0], sol[1]
        r = float(np.sqrt(max(sol[2] + cx * cx + cy * cy, 0)))
        if r < 1e-6:
            continue
        rad = np.linalg.norm(xy - [cx, cy], axis=1)
        if rad.std() / r > CYL_RADIAL_TOL:
            continue
        center = mean + a * cx + b * cy
        t = (pts - center) @ axis
        # inward-facing normals => hole (material outside the cylinder); outward => boss/pin
        radial = pts - center - np.outer(t, axis)
        radial /= (np.linalg.norm(radial, axis=1)[:, None] + 1e-12)
        outward = float((np.einsum("ij,ij->i", n, radial)).mean()) > 0
        spread = np.arctan2(xy[:, 1] - cy, xy[:, 0] - cx)
        full = len(np.unique(np.round(spread, 1))) > 50     # wraps (almost) all the way round
        out.append({"kind": "cylinder", "role": "boss" if outward else "hole", "radius": round(r, 3),
                    "diameter": round(2 * r, 3), "length": round(float(t.max() - t.min()), 3),
                    "axis": _round(axis), "center": _round(center), "full_round": bool(full),
                    "faces": len(c), "face_ids": [int(i) for i in c[:MAX_IDS]], "ids_truncated": len(c) > MAX_IDS, "approximate": True})
    out.sort(key=lambda d: -d["faces"])
    return out


_cache: "OrderedDict[str, dict]" = OrderedDict()


def detect(m: trimesh.Trimesh) -> dict:
    """Cached by mesh content, so repeated requests while editing/selecting cost nothing."""
    key = hashlib.sha1(np.ascontiguousarray(m.vertices, dtype=np.float64).tobytes() + np.ascontiguousarray(m.faces, dtype=np.int64).tobytes()).hexdigest()
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    r = _detect(m)
    _cache[key] = r
    while len(_cache) > CACHE_MAX:
        _cache.popitem(last=False)
    return r


def _detect(m: trimesh.Trimesh) -> dict:
    if len(m.faces) > MAX_FACES:
        return {"ok": False, "reason": f"Too many triangles ({len(m.faces)}) to analyse; simplify first.",
                "planes": [], "cylinders": [], "holes": [], "approximate": True}
    if len(m.faces) == 0:
        return {"ok": True, "planes": [], "cylinders": [], "holes": [], "approximate": True}
    planes = planar_faces(m)
    cyls = cylinders(m, planes)
    holes = [c for c in cyls if c["role"] == "hole" and c["full_round"]]
    return {"ok": True, "approximate": True,
            "note": "Detected from the triangle mesh with tolerances; shapes are approximate, not exact CAD geometry.",
            "planes": planes[:MAX_REPORT], "cylinders": cyls[:MAX_REPORT], "holes": holes[:MAX_REPORT],
            "counts": {"planes": len(planes), "cylinders": len(cyls), "holes": len(holes)}}
