"""FDM Slicer tab only: a big binary STL welded and simplified straight from its bytes (same method as TorchC0's lean load).

A 2.1M-triangle STL counts as 6.3M corners against the shared upload gate (415) and trimesh's load of it peaks near
1.7 GB in the server process. The FDM tab sends fdm_big=1, and such files are reduced to FDM_MAX_FACES triangles in
core/guard.py's child before the gate and the normal import, so the project, the viewer and the slicer stay light."""
from __future__ import annotations

import os
import struct

from . import meshedit

FDM_MAX_FACES = int(os.environ.get("ZEIM_FDM_MAX_FACES", "400000"))
FDM_AS_MB = int(os.environ.get("ZEIM_FDM_AS_MB", "4096"))   # address space of the simplify process (its RSS peaks ~0.65 GB for 2.1M triangles)


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
    v, f = u.view("<f4").reshape(-1, 3).copy(), inv.reshape(-1, 3).astype(np.int32)     # float32/int32: half the memory
    del u, inv
    f = f[(f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])]
    if len(f) > max_faces:
        v, f = fs.simplify(v, f, target_reduction=1 - max_faces / len(f), agg=7)
    used = np.unique(f)
    remap = np.zeros(len(v), np.int32); remap[used] = np.arange(len(used))
    v, f = v[used].astype("<f4"), remap[f]
    t = v[f]                                               # (k,3,3)
    nrm = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    ln = np.linalg.norm(nrm, axis=1, keepdims=True); ln[ln == 0] = 1
    out = np.zeros(len(f), rec)
    out["n"] = (nrm / ln).astype("<f4"); out["v"] = t
    return b"ZEIM FDM simplified".ljust(80, b" ") + struct.pack("<I", len(f)) + out.tobytes(), n, len(f)


# ---- run in a fresh interpreter, not a fork of the server ----
# A fork inherits the ~1.1 GB server heap and Python's refcounting/gc copies those pages, so the guard child of a
# 2.1M-triangle STL reached 1.7 GB and the 3 GB container OOM-killed it. A new interpreter needs only ~1 GB.
import threading as _th

_one = _th.BoundedSemaphore(1)


class Busy(Exception):
    pass


class TooBig(Exception):
    pass


def _limit():
    import resource
    mb = FDM_AS_MB
    resource.setrlimit(resource.RLIMIT_AS, (mb * 2**20, mb * 2**20))


def shrink_isolated(data: bytes, timeout: float = 240, wait: float = 120) -> tuple[bytes, int, int]:
    import subprocess
    import sys
    import tempfile
    from pathlib import Path
    if not _one.acquire(timeout=wait):
        raise Busy()
    try:
        with tempfile.TemporaryDirectory(prefix="fdmlean-") as d:
            src, dst = Path(d) / "in.stl", Path(d) / "out.stl"
            src.write_bytes(data)
            root = str(Path(__file__).resolve().parents[2])
            try:
                p = subprocess.run([sys.executable, "-m", "app.core.fdmlean", str(src), str(dst), str(FDM_MAX_FACES)], cwd=root,
                                   capture_output=True, text=True, timeout=timeout, preexec_fn=_limit,
                                   env={**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"})
            except subprocess.TimeoutExpired:
                raise TooBig()
            if p.returncode == 3:
                raise meshedit.OpError(p.stdout.strip() or "File contains invalid coordinates.")
            if p.returncode != 0 or not dst.exists():
                raise TooBig()
            n, k = map(int, p.stdout.split()[-2:])
            return dst.read_bytes(), n, k
    finally:
        _one.release()


if __name__ == "__main__":
    import sys
    from pathlib import Path
    try:
        import mmap
        with open(sys.argv[1], "rb") as fh:                 # mapped, not read: file pages are reclaimable, not anon memory
            buf = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
            out, n, k = shrink(buf, int(sys.argv[3]) if len(sys.argv) > 3 else None)
    except meshedit.OpError as e:
        print(e)
        sys.exit(3)
    Path(sys.argv[2]).write_bytes(out)
    print(n, k)
