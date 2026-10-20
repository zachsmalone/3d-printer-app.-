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
THIN_MIN_SPOTS = 2              # ... or this many sampled spots thinner than one line (same rule as /printcheck; QA B11)
MIN_FILAMENT_G = 0.01           # a slice that uses less filament than this printed (almost) nothing


def bed_fit(size, printer_id) -> dict:
    bed = ps.bed_of(printer_id)
    fits = all(d <= b + FIT_TOLERANCE_MM for d, b in zip(size, bed))
    scale = min(b / d for d, b in zip(size, bed) if d > 0) if size and max(size) > 0 else 1.0
    return {"ok": fits, "size_mm": [round(v, 1) for v in size], "bed_mm": list(bed),
            "fit_scale_pct": None if fits else max(1, int(scale * 100))}


THIN_MAX_FACES = 150_000     # above this the ray-cast index costs GBs: skip with a note (QA B1)


def thin_walls(mesh: trimesh.Trimesh, min_mm: float) -> dict:
    """Bounded wrapper: size cap first, then the ray cast in a memory-capped child (core/guard.py)."""
    if len(mesh.faces) > THIN_MAX_FACES:
        return {"ok": None, "skipped": "too_detailed", "thin_fraction": None, "min_mm": min_mm,
                "note": f"Thin-wall check skipped: the model has {len(mesh.faces):,} triangles (checked up to {THIN_MAX_FACES:,})."}
    from ..core import guard
    try:
        return guard.run(_thin_walls, mesh, min_mm, mem_mb=1200, timeout=60)
    except (guard.Tripped, guard.Busy, MemoryError, OSError):     # QA B1/B11: a MemoryError used to escape and the badge fell back to "Fits: not sliced yet"
        return {"ok": None, "skipped": "limit", "thin_fraction": None, "min_mm": min_mm,
                "note": "Thin-wall check skipped: it needed more memory or time than allowed."}


def _thin_walls(mesh: trimesh.Trimesh, min_mm: float) -> dict:
    """Cast a ray inward from sampled surface points; the distance to the opposite surface is the local wall thickness."""
    if len(mesh.faces) == 0:
        return {"ok": False, "thin_fraction": 1.0, "min_mm": min_mm}
    rng = np.random.default_rng(0)
    n = min(THIN_SAMPLES, len(mesh.faces))
    idx = rng.choice(len(mesh.faces), n, replace=False, p=mesh.area_faces / mesh.area_faces.sum()) if mesh.area > 0 else np.arange(n)
    normals = mesh.face_normals[idx]
    origins = mesh.triangles_center[idx] - normals * 1e-4
    try:
        from ..core.thickness import first_hits_faces, real_thin
        locs, ray_idx, hit = first_hits_faces(mesh, origins, -normals)   # batched: small child memory (N3)
    except Exception:
        return {"ok": None, "thin_fraction": None, "min_mm": min_mm}
    if len(ray_idx) == 0:
        return {"ok": True, "thin_fraction": 0.0, "min_mm": min_mm}
    d = np.linalg.norm(locs - origins[ray_idx], axis=1)
    thin = real_thin(mesh, idx[ray_idx], hit, d, min_mm)             # same shell + nearly parallel opposite face (same rule as /printcheck)
    d = np.where(thin | (d >= min_mm), d, min_mm)
    thin_n = int(np.count_nonzero(thin))
    frac = float(thin_n) / n
    # QA B11: a few spots far below one line (0.06 mm on a 0.42 mm line) used to pass the 5 % rule while /printcheck
    # flagged them; any couple of sampled spots under one line now counts, like printcheck's "some thin spots".
    return {"ok": frac <= THIN_FAIL_FRACTION and thin_n < THIN_MIN_SPOTS, "thin_fraction": round(frac, 3), "thin_count": thin_n,
            "min_mm": min_mm, "thinnest_mm": round(float(d.min()), 3)}


PIP_CLEARANCE_FDM = 0.3      # safe print-in-place gap between separate parts (hinge knuckles, pins, joints, chain links)
PIP_CLEARANCE_RESIN = 0.15
GAP_MAX_FACES = 200_000


def part_gaps(mesh: trimesh.Trimesh, safe_mm: float) -> dict:
    """Smallest gap between separate bodies that are close together (print-in-place parts). Non-blocking warning only.
    Bodies that touch or overlap (gap ~0) are treated as joined, not as a print-in-place gap."""
    out = {"ok": True, "safe_mm": safe_mm, "min_gap_mm": None, "warning": None}
    if len(mesh.faces) == 0 or len(mesh.faces) > GAP_MAX_FACES:
        return out
    try:
        parts = mesh.split(only_watertight=False)
    except Exception:
        return out
    if len(parts) < 2 or len(parts) > 60:
        return out
    from scipy.spatial import cKDTree
    pts = []
    for p in parts:
        n = min(3000, max(200, len(p.faces) * 2))
        v, _ = trimesh.sample.sample_surface(p, n, seed=0)
        pts.append(np.vstack([v, p.vertices]))
    trees = [cKDTree(x) for x in pts]
    best = None
    for i in range(len(parts)):
        for j in range(i + 1, len(parts)):
            lo, hi = parts[i].bounds, parts[j].bounds                 # skip pairs far apart
            if np.any(lo[0] - hi[1] > safe_mm * 2) or np.any(hi[0] - lo[1] > safe_mm * 2):
                continue
            d, _ = trees[j].query(pts[i], k=1)
            g = float(d.min())
            if g < 0.02:                                              # touching / fused: not a gap
                continue
            best = g if best is None else min(best, g)
    if best is None:
        return out
    out["min_gap_mm"] = round(best, 2)
    if best < safe_mm:
        out["ok"] = False
        out["warning"] = (f"These parts are {best:.2f} mm apart and may fuse together. Aim for at least {safe_mm:g} mm. "
                          "You can still slice it.")
    return out


def _inside_out(mesh: trimesh.Trimesh) -> bool:
    """A closed mesh whose signed volume is negative has every face pointing inward."""
    try:
        return bool(len(mesh.faces) and mesh.is_watertight and float(mesh.volume) < 0)
    except Exception:
        return False


def check(mesh: trimesh.Trimesh, printer_id=None, nozzle=None, slices_ok=None, slice_message="", filament_g=None) -> dict:
    pid, n = ps.resolve(printer_id, nozzle)
    p = ps.printer_public(pid)
    size = tuple(float(v) for v in mesh.extents) if len(mesh.vertices) else (0.0, 0.0, 0.0)
    fit = bed_fit(size, pid)
    min_wall = ps.line_width(n) if n else 0.4      # resin: 0.4 mm is a common minimum wall
    thin = thin_walls(mesh, min_wall)
    inside_out = _inside_out(mesh)
    gaps = part_gaps(mesh, PIP_CLEARANCE_FDM if n else PIP_CLEARANCE_RESIN)
    checks = {"bed_fit": fit, "thin_wall": thin, "slices": {"ok": slices_ok, "message": slice_message, "filament_g": filament_g},
              "inside_out": {"ok": not inside_out}, "gaps": gaps}
    # B11: a part thinner than one line, or a speck only a few lines across, won't really print
    tiny = bool(size) and (min(size) < min_wall or max(size) < 5 * min_wall)
    if tiny:
        thin = {**thin, "ok": False, "note": f"The whole part is tiny for a {min_wall:g} mm line."}
        checks["thin_wall"] = thin
    states = [fit["ok"], thin["ok"], slices_ok]
    # B11: a slice that used ~0 g of filament printed nothing, whatever the geometry checks say
    empty = slices_ok is True and filament_g is not None and float(filament_g) < MIN_FILAMENT_G
    if fit["ok"] is False or slices_ok is False:
        verdict, label = "no", "Won't print as is"
    elif inside_out:                      # QA: an inside-out (inverted) cube used to get "Will print"
        verdict, label = "maybe", "Might print: model is inside out"
    elif thin["ok"] is False:
        verdict, label = "maybe", "Might print: thin walls"
    elif empty:
        verdict, label = "maybe", "Might print: almost no filament"
    elif thin["ok"] is None:              # skipped / timed out / unmeasurable: never claim "Will print" (N3)
        verdict, label = "unchecked", ("Sliced OK; thin-wall check skipped" if slices_ok else "Fits; thin-wall check skipped")
    elif all(s is True for s in states):
        verdict, label = "yes", "Will print"
    else:
        verdict, label = "likely", "Fits: not sliced yet"
    tips = []
    if not fit["ok"]:
        tips.append(f"It won't fit your bed. Scale it to about {fit['fit_scale_pct']}% to fit the {p['name']} "
                    f"({' x '.join(f'{b:g}' for b in fit['bed_mm'])} mm), use shrink-to-fit (\"Scale down to fit this printer\") when you slice, or cut it into pieces with Edit → Split.")
    if thin["ok"] is None and fit["ok"] is not False and slices_ok is not False:
        tips.append((thin.get("note") or "The thin-wall check could not run.") + " Check thin parts in the slicer preview, or Simplify and check again.")
    if thin["ok"] is False:
        tips.append(f"Some walls are thinner than one {min_wall:g} mm line"
                    + (f" (thinnest about {thin['thinnest_mm']:g} mm)" if (thin.get("thinnest_mm") or min_wall) < min_wall else "")
                    + ". Try a smaller nozzle or thicken them.")
    if gaps["ok"] is False:
        tips.append(gaps["warning"])                                  # warning only: never changes the verdict or blocks slicing
    if inside_out:
        tips.append("The model is inside out (its surfaces face inward), so slicers may print it wrongly or not at all. Run Smart Fix to turn it the right way out.")
    if empty:
        tips.append(f"The slicer used almost no filament ({float(filament_g):.2f} g), so little or nothing would print. "
                    f"The part may be too small or too thin for a {min_wall:g} mm line.")
    if slices_ok is False:
        tips.append(slice_message or "The slicer couldn't process it. Try Smart Fix first.")
    warnings = [gaps["warning"]] if gaps["ok"] is False else []
    return {"verdict": verdict, "label": label, "warnings": warnings, "printer_id": pid, "printer": p["name"], "nozzle": n, "checks": checks, "tips": tips}


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
