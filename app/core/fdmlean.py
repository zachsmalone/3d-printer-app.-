"""FDM Slicer tab only: a big binary STL welded and simplified straight from its bytes (same method as TorchC0's lean load).

A 2.1M-triangle STL counts as 6.3M corners against the shared upload gate (415) and trimesh's load of it peaks near
1.7 GB in the server process. The FDM tab sends fdm_big=1, and such files are reduced to FDM_MAX_FACES triangles in
core/guard.py's child before the gate and the normal import, so the project, the viewer and the slicer stay light."""
from __future__ import annotations

import os
import struct

from . import meshedit

FDM_MAX_FACES = int(os.environ.get("ZEIM_FDM_MAX_FACES", "400000"))
FDM_MEM_MB = int(os.environ.get("ZEIM_FDM_MEM_MB", "2000"))


def faces_if_big(data: bytes, max_faces: int = None) -> int:
    """Triangle count when data is a binary STL above max_faces (and within meshedit.MAX_FACES), else 0."""
    max_faces = FDM_MAX_FACES if max_faces is None else max_faces
    if len(data) < 84:
        return 0
    n = int.from_bytes(data[80:84], "little")
    if n <= max_faces or len(data) != 84 + 50 * n or n > meshedit.MAX_FACES:
        return 0
    return n


def shrink(data: bytes, max_faces: int = None) -> tuple[bytes, int, int]:
    """(binary STL bytes with <= max_faces triangles, original count, new count). Raises meshedit.OpError on bad data."""
    max_faces = FDM_MAX_FACES if max_faces is None else max_faces
    n = faces_if_big(data, max_faces)
    if not n:
        raise ValueError("not a big binary STL")
    import numpy as np
    import fast_simplification as fs
    rec = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    tri = np.ascontiguousarray(np.frombuffer(data, rec, count=n, offset=84)["v"].reshape(-1, 3))
    if not np.isfinite(tri).all():
        raise meshedit.OpError("File contains invalid coordinates.")
    u, inv = np.unique(tri.view(np.dtype((np.void, 12))).ravel(), return_inverse=True)
    del tri
    v, f = u.view("<f4").reshape(-1, 3).astype(np.float64), inv.reshape(-1, 3).astype(np.int64)
    del u, inv
    f = f[(f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])]
    if len(f) > max_faces:
        v, f = fs.simplify(v, f, target_reduction=1 - max_faces / len(f), agg=7)
    used = np.unique(f)
    remap = np.zeros(len(v), np.int64); remap[used] = np.arange(len(used))
    v, f = v[used].astype("<f4"), remap[f]
    t = v[f]                                               # (k,3,3)
    nrm = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    ln = np.linalg.norm(nrm, axis=1, keepdims=True); ln[ln == 0] = 1
    out = np.zeros(len(f), rec)
    out["n"] = (nrm / ln).astype("<f4"); out["v"] = t
    return b"ZEIM FDM simplified".ljust(80, b" ") + struct.pack("<I", len(f)) + out.tobytes(), n, len(f)
