"""'Will it print?' checks for the chosen printer + nozzle: bed fit, slices OK, thin walls.

bed_fit and thin_wall are geometry checks (fast, no slicer). slices is the real PrusaSlicer run when one was done
(None = not checked yet), so a badge never claims more than was actually tested."""
from __future__ import annotations

import numpy as np
import trimesh

from app.services import print_setup as ps

FIT_TOLERANCE_MM = 0.05
THIN_SAMPLES = 1500
THIN_FAIL_FRACTION = 0.05       # more than 5 % of the surface (by sample) thinner than one line width -> warning


def bed_fit(size, printer_id) -> dict:
    bed = ps.bed_of(printer_id)
    fits = all(d <= b + FIT_TOLERANCE_MM for d, b in zip(size, bed))
    scale = min(b / d for d, b in zip(size, bed) if d > 0) if size and max(size) > 0 else 1.0
    return {"ok": fits, "size_mm": [round(v, 1) for v in size], "bed_mm": list(bed),
            "fit_scale_pct": None if fits else max(1, int(scale * 100))}


def thin_walls(mesh: trimesh.Trimesh, min_mm: float) -> dict:
    """Cast a ray inward from sampled surface points; the distance to the opposite surface is the local wall thickness."""
    if len(mesh.faces) == 0:
        return {"ok": False, "thin_fraction": 1.0, "min_mm": min_mm}
    rng = np.random.default_rng(0)
    n = min(THIN_SAMPLES, len(mesh.faces))
    idx = rng.choice(len(mesh.faces), n, replace=False, p=mesh.area_faces / mesh.area_faces.sum()) if mesh.area > 0 else np.arange(n)
    normals = mesh.face_normals[idx]
    origins = mesh.triangles_center[idx] - normals * 1e-4
    try:
        locs, ray_idx, _ = mesh.ray.intersects_location(origins, -normals, multiple_hits=False)
    except Exception:
        return {"ok": None, "thin_fraction": None, "min_mm": min_mm}
    if len(ray_idx) == 0:
        return {"ok": True, "thin_fraction": 0.0, "min_mm": min_mm}
    d = np.linalg.norm(locs - origins[ray_idx], axis=1)
    frac = float(np.count_nonzero(d < min_mm)) / n
    return {"ok": frac <= THIN_FAIL_FRACTION, "thin_fraction": round(frac, 3), "min_mm": min_mm,
            "thinnest_mm": round(float(d.min()), 2)}


def check(mesh: trimesh.Trimesh, printer_id=None, nozzle=None, slices_ok=None, slice_message="") -> dict:
    pid, n = ps.resolve(printer_id, nozzle)
    p = ps.printer_public(pid)
    size = tuple(float(v) for v in mesh.extents) if len(mesh.vertices) else (0.0, 0.0, 0.0)
    fit = bed_fit(size, pid)
    min_wall = ps.line_width(n) if n else 0.4      # resin: 0.4 mm is a common minimum wall
    thin = thin_walls(mesh, min_wall)
    checks = {"bed_fit": fit, "thin_wall": thin, "slices": {"ok": slices_ok, "message": slice_message}}
    states = [fit["ok"], thin["ok"], slices_ok]
    if fit["ok"] is False or slices_ok is False:
        verdict, label = "no", "Won't print as is"
    elif thin["ok"] is False:
        verdict, label = "maybe", "Might print: thin walls"
    elif all(s is True for s in states):
        verdict, label = "yes", "Will print"
    else:
        verdict, label = "likely", "Fits: not sliced yet"
    tips = []
    if not fit["ok"]:
        tips.append(f"It won't fit your bed. Scale it to about {fit['fit_scale_pct']}% to fit the {p['name']} "
                    f"({' x '.join(f'{b:g}' for b in fit['bed_mm'])} mm), use shrink-to-fit (\"Scale down to fit this printer\") when you slice, or cut it into pieces with Edit → Split.")
    if thin["ok"] is False:
        tips.append(f"Some walls are thinner than one {min_wall:g} mm line. Try a smaller nozzle or thicken them.")
    if slices_ok is False:
        tips.append(slice_message or "The slicer couldn't process it. Try Smart Fix first.")
    return {"verdict": verdict, "label": label, "printer_id": pid, "printer": p["name"], "nozzle": n, "checks": checks, "tips": tips}


def check_file(path, printer_id=None, nozzle=None, **kw) -> dict:
    mesh = trimesh.load(str(path), force="mesh", process=False)
    return check(mesh, printer_id, nozzle, **kw)


# Geometry checks are CPU-heavy on big meshes (ray casting): run them in ONE worker process so the web server's
# threads (and the GIL) stay free for everything else, and cache results per file version + printer + nozzle.
_pool = None
_cache: dict = {}


def _watch_parent(parent: int):
    """Worker initializer: exit as soon as the server process is gone (SIGTERM'd servers never shut the pool down,
    which left 370 MB orphans behind)."""
    import os, threading, time
    def loop():
        while True:
            if os.getppid() != parent:
                os._exit(0)
            time.sleep(1)
    threading.Thread(target=loop, daemon=True).start()


def _shutdown():
    global _pool
    if _pool is not None:
        _pool.shutdown(wait=False, cancel_futures=True)
        _pool = None


def _worker(path, printer_id, nozzle, kw):
    return check_file(path, printer_id, nozzle, **kw)


async def check_file_async(path, printer_id=None, nozzle=None, **kw) -> dict:
    import asyncio, os
    from concurrent.futures import ProcessPoolExecutor
    global _pool
    st = os.stat(path)
    key = (str(path), st.st_size, st.st_mtime_ns, printer_id, nozzle, tuple(sorted(kw.items())))
    if key in _cache:
        return _cache[key]
    if os.environ.get("PHOTO3D_WILLPRINT_INLINE") or st.st_size < 2_000_000:
        res = check_file(path, printer_id, nozzle, **kw)              # small files: cheap enough inline
    else:
        if _pool is None:
            import multiprocessing as mp
            import atexit
            _pool = ProcessPoolExecutor(max_workers=1, mp_context=mp.get_context("spawn"), initializer=_watch_parent, initargs=(os.getpid(),))
            atexit.register(_shutdown)
        res = await asyncio.get_running_loop().run_in_executor(_pool, _worker, str(path), printer_id, nozzle, kw)
    if len(_cache) > 500:
        _cache.clear()
    _cache[key] = res
    return res
