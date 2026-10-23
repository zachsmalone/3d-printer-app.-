"""Geometry fingerprints for the Showcase duplicate check (theft protection).

Also invariant to MIRRORING (the principal-axis frame and the sign rule absorb reflections; the voxel grid is
compared over all 8 sign flips) and, within limits, to RE-MESHING (a subdivided or lightly decimated copy with
different vertex counts still matches when compactness, axes, D2 histogram and voxel overlap all agree tightly).

A fingerprint describes a mesh's SHAPE, not its file: renaming, re-exporting, uniform scaling, moving and rotating
the model leave it unchanged. It has two parts:

* `exact`: sha256 of the normalized mesh (centred on the centroid, rotated onto its principal axes with a
  deterministic sign rule, scaled to unit RMS radius, vertices rounded and sorted). Equal hashes = same mesh.
* `features`: vertex/face counts, compactness (volume / area^1.5), sorted principal-axis ratios and a D2 shape
  distribution (histogram of distances between seeded random surface point pairs, divided by their mean).

`similar()` compares two fingerprints with fixed tolerances. Limits (honest): it is a screen, not proof. It will NOT
catch a model that was edited (parts added/cut, remeshed/decimated heavily, non-uniform scaling, mirrored halves
merged, a bust put on a new base), and two different but very simple shapes (two plain cubes) can look alike.
Matches only ever hold an upload for a human moderator; nothing is deleted automatically.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

VERSION = 1
BINS = 32
SAMPLES = 4096

# tolerances for a near-match (all must hold, or the exact hash must be equal)
COUNT_TOL = 0.02          # vertex / face counts within 2%
COMPACT_TOL = 0.03        # compactness within 3% (relative)
AXIS_TOL = 0.03           # each principal-axis ratio within 0.03
HIST_TOL = 0.10           # L1 distance between D2 histograms (each sums to 1)
# re-meshed copies (vertex/face counts differ by more than COUNT_TOL) need a stricter shape agreement instead
VOX = 8                   # coarse occupancy grid (VOX^3 cells) of surface samples in the normalized frame
VOX_TOL = 0.80            # min Jaccard overlap of occupied cells (best of the 8 axis sign flips: mirror-proof)
REMESH_HIST_TOL = 0.06    # D2 L1 limit when counts differ
REMESH_COMPACT_TOL = 0.02


def _load(path):
    import trimesh
    m = trimesh.load(str(path), force="mesh", process=True)
    if not isinstance(m, trimesh.Trimesh) or len(m.faces) == 0:
        raise ValueError("no mesh")
    m.merge_vertices()
    return m


def _normalize(v: np.ndarray, w: np.ndarray | None = None):
    """Centre, align to principal axes (largest first) with skew-based signs, scale to unit RMS radius."""
    c = v.mean(axis=0) if w is None else (v * w[:, None]).sum(axis=0) / w.sum()
    x = v - c
    cov = np.cov(x.T) if w is None else (x * w[:, None]).T @ x / w.sum()
    evals, evecs = np.linalg.eigh(cov)
    order = np.argsort(evals)[::-1]
    evals, evecs = evals[order], evecs[:, order]
    y = x @ evecs
    for k in range(3):                                   # sign rule: heavier tail on the + side
        if np.sum(y[:, k] ** 3) < 0:
            y[:, k] = -y[:, k]
    rms = float(np.sqrt((y ** 2).sum(axis=1).mean())) or 1.0
    return y / rms, np.clip(evals, 0, None)


def compute(path) -> dict:
    m = _load(path)
    v = np.asarray(m.vertices, dtype=float)
    area = float(m.area) or 1e-12
    vol = abs(float(m.volume)) if (m.is_volume or m.is_watertight) else 0.0   # flipped normals: same shape
    # principal axes from area-weighted face centres (robust to uneven vertex density)
    fc = np.asarray(m.triangles_center, dtype=float)
    _, ev = _normalize(fc, np.asarray(m.area_faces, dtype=float) + 1e-18)
    s = np.sqrt(ev)
    axes = [float(s[1] / s[0]) if s[0] else 0.0, float(s[2] / s[0]) if s[0] else 0.0]
    # exact hash of the normalized mesh
    nv, _ = _normalize(v)
    q = np.round(nv, 4) + 0.0                            # +0.0 folds -0.0 into 0.0
    rows = q[np.lexsort(q.T[::-1])]
    h = hashlib.sha256(rows.astype("<f8").tobytes() + f"|{len(m.faces)}".encode()).hexdigest()
    # D2 shape distribution with a fixed seed: deterministic for the same mesh
    rng = np.random.default_rng(12345)
    pts = _sample(m, rng)
    i, j = rng.integers(0, len(pts), (2, SAMPLES * 2))
    d = np.linalg.norm(pts[i] - pts[j], axis=1)
    d = d / (d.mean() or 1.0)
    hist, _ = np.histogram(d, bins=BINS, range=(0.0, 3.0))
    hist = hist / max(1, hist.sum())
    vox = _voxels(pts)
    return {"v": VERSION, "exact": h, "vertices": int(len(v)), "faces": int(len(m.faces)),
            "compactness": round(vol / area ** 1.5, 6), "axes": [round(a, 5) for a in sorted(axes, reverse=True)],
            "d2": [round(float(x), 5) for x in hist], "vox": vox}


def _voxels(pts: np.ndarray) -> str:
    """Hex bitmask of occupied cells of a VOX^3 grid over the PCA-aligned, RMS-scaled surface samples."""
    y, _ = _normalize(pts)
    lim = 2.0
    idx = np.clip(((y + lim) / (2 * lim) * VOX).astype(int), 0, VOX - 1)
    bits = np.zeros(VOX ** 3, dtype=np.uint8)
    bits[(idx[:, 0] * VOX + idx[:, 1]) * VOX + idx[:, 2]] = 1
    return np.packbits(bits).tobytes().hex()


def _grid(h: str) -> np.ndarray:
    return np.unpackbits(np.frombuffer(bytes.fromhex(h), dtype=np.uint8))[: VOX ** 3].reshape(VOX, VOX, VOX).astype(bool)


def voxel_overlap(a: str | None, b: str | None) -> float | None:
    """Best Jaccard overlap over the 8 axis sign flips (covers mirrored copies and near-symmetric sign ties)."""
    if not a or not b:
        return None
    ga, gb = _grid(a), _grid(b)
    best = 0.0
    for fx in (False, True):
        for fy in (False, True):
            for fz in (False, True):
                g = gb[::-1 if fx else 1, ::-1 if fy else 1, ::-1 if fz else 1]
                u = np.logical_or(ga, g).sum()
                best = max(best, float(np.logical_and(ga, g).sum() / u) if u else 0.0)
    return best


def _sample(m, rng) -> np.ndarray:
    """Area-weighted random points on the surface (own implementation, seeded)."""
    tri = np.asarray(m.triangles, dtype=float)
    a = np.asarray(m.area_faces, dtype=float)
    p = a / a.sum() if a.sum() > 0 else None
    f = rng.choice(len(tri), SAMPLES, p=p)
    r1, r2 = rng.random(SAMPLES), rng.random(SAMPLES)
    sq = np.sqrt(r1)
    t = tri[f]
    return (1 - sq)[:, None] * t[:, 0] + (sq * (1 - r2))[:, None] * t[:, 1] + (sq * r2)[:, None] * t[:, 2]


def _rel(a, b) -> float:
    return abs(a - b) / max(abs(a), abs(b), 1e-12)


def similar(a: dict | None, b: dict | None) -> dict | None:
    """None when not a match; else {"exact": bool, "score": 0..1 (1 = identical features)}."""
    if not a or not b or a.get("v") != b.get("v"):
        return None
    if a["exact"] == b["exact"]:
        return {"exact": True, "score": 1.0}
    remesh = _rel(a["vertices"], b["vertices"]) > COUNT_TOL or _rel(a["faces"], b["faces"]) > COUNT_TOL
    vo = voxel_overlap(a.get("vox"), b.get("vox"))
    if remesh and vo is None:
        return None                                      # old fingerprints without a voxel grid: counts must agree
    if _rel(a["compactness"], b["compactness"]) > (REMESH_COMPACT_TOL if remesh else COMPACT_TOL):
        return None
    if any(abs(x - y) > AXIS_TOL for x, y in zip(a["axes"], b["axes"])):
        return None
    l1 = float(np.abs(np.asarray(a["d2"]) - np.asarray(b["d2"])).sum())
    tol = REMESH_HIST_TOL if remesh else HIST_TOL
    if l1 > tol or (vo is not None and vo < VOX_TOL):
        return None
    return {"exact": False, "score": round(1 - l1 / tol, 3), "remeshed": remesh,
            "voxel_overlap": None if vo is None else round(vo, 3)}


def safe_compute(path) -> dict | None:
    """Never blocks a publish: an unreadable mesh simply has no fingerprint."""
    try:
        return compute(Path(path)) if path and Path(path).is_file() else None
    except Exception:
        return None
