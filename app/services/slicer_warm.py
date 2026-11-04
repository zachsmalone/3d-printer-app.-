"""PERF8: keep the PrusaSlicer engine warm.

PrusaSlicer has no server mode, so every slice starts a fresh process. What CAN be kept ready is the
engine binary, its shared libraries and the profile code path in the OS page cache: after a deploy or a
quiet spell, the first slice otherwise pays to read ~36 MB of binary plus libraries from disk.

This runs one tiny 10 mm cube slice (nice 19) shortly after start-up, and again after
ZEIM_SLICER_WARM_MIN minutes (default 20) without any real slice. ZEIM_SLICER_WARM=0 turns it off.
Numbers and method: reports/perf8-slicer-warmup.md (tools/perf8_bench.py)."""
from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
from pathlib import Path

log = logging.getLogger("zeim.slicer_warm")
_last_slice = 0.0          # monotonic time of the last real or warm-up slice


def note_slice() -> None:
    global _last_slice
    _last_slice = time.monotonic()


def enabled() -> bool:
    if "ZEIM_SLICER_WARM" not in os.environ and "PYTEST_CURRENT_TEST" in os.environ:
        return False          # no background slicing inside the test suite
    return (os.environ.get("ZEIM_SLICER_WARM") or "1").strip().lower() not in ("0", "false", "no", "off")


def idle_minutes() -> float:
    try:
        return max(1.0, float(os.environ.get("ZEIM_SLICER_WARM_MIN") or 20))
    except ValueError:
        return 20.0


def cube_stl(path: Path, s: float = 10.0) -> Path:
    import trimesh
    trimesh.creation.box(extents=(s, s, s)).export(path)
    return path


def warm_once() -> float | None:
    """One tiny slice; returns seconds, or None when the engine is missing or fails (never raises)."""
    from app.services import slice_engine as se
    if se.find_engine() is None:
        return None
    t0 = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="zeim-warm-") as td:
            prof, _ = se.profile_for()
            se.slice_model_path(cube_stl(Path(td) / "cube.stl"), prof, Path(td) / "cube.gcode")
    except Exception as e:  # warm-up must never hurt the app
        log.warning("slicer warm-up failed: %s", e)
        return None
    dt = time.monotonic() - t0
    note_slice()
    log.info("slicer warm-up slice took %.2fs", dt)
    return dt


def start_background(first_delay_s: float = 20.0) -> threading.Thread | None:
    if not enabled():
        log.info("slicer warm-up off (ZEIM_SLICER_WARM=0)")
        return None

    def loop():
        try:
            os.nice(19)
        except OSError:
            pass
        time.sleep(first_delay_s)
        while True:
            if time.monotonic() - _last_slice >= idle_minutes() * 60 or _last_slice == 0.0:
                warm_once()
            time.sleep(60)

    t = threading.Thread(target=loop, name="zeim-slicer-warm", daemon=True)
    t.start()
    return t
