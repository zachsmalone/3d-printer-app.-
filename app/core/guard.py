"""Runtime ceiling for heavy geometry work (CADRT-1 / QA B1 / B4).

Pre-flight estimates can be wrong, so heavy ops also run in a forked child process with a hard
address-space limit (RLIMIT_AS) and a wall-clock timeout. If the child runs out of memory, crashes
or times out, the caller gets a friendly OpError/None and nothing in the parent (the scene, the
project) has changed. The parent's memory never grows with the op.
"""
from __future__ import annotations

import multiprocessing as mp
import os
import pickle
import resource
import threading
import traceback

MEM_MB = int(os.environ.get("PHOTO3D_HEAVY_MEM_MB", "1500"))     # extra address space on top of the parent's
TIMEOUT_S = float(os.environ.get("PHOTO3D_HEAVY_TIMEOUT_S", "120"))
ENABLED = os.environ.get("PHOTO3D_HEAVY_GUARD", "1") != "0"
MAX_CHILDREN = max(1, int(os.environ.get("PHOTO3D_HEAVY_CHILDREN", "2")))   # per process (CADRT-9)
WAIT_S = float(os.environ.get("PHOTO3D_HEAVY_WAIT_S", "20"))
_slots = threading.BoundedSemaphore(MAX_CHILDREN)
MIN_HEADROOM = 64 * 1024 * 1024


class Busy(Exception):
    """All guarded slots are in use; the caller should say 'busy, try again'."""


class Tripped(Exception):
    """The child hit the memory/time ceiling or died."""


def _vm_bytes() -> int:
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith("VmSize:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        pass
    return 0


def _clamp(want: int) -> int | None:
    """Never try to RAISE an existing RLIMIT_AS (CADRT-8): use min(want, soft, hard).
    Returns the limit to set, 0 for 'keep the inherited limit as is', or None if there is no usable headroom."""
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    caps = [x for x in (soft, hard) if x not in (resource.RLIM_INFINITY, -1)]
    limit = min([want] + caps)
    if limit - _vm_bytes() < MIN_HEADROOM:
        return None
    return 0 if caps and limit == min(caps) else limit


def _child(conn, fn, args, kwargs, limit):
    try:
        if limit:
            try:
                soft, hard = resource.getrlimit(resource.RLIMIT_AS)
                resource.setrlimit(resource.RLIMIT_AS, (limit, hard))
            except (ValueError, OSError):
                pass                                   # keep the inherited (tighter) limit
        os.environ["OMP_NUM_THREADS"] = "1"
        res = ("ok", fn(*args, **kwargs))
    except MemoryError:
        res = ("mem", None)
    except BaseException as e:   # noqa: BLE001 - shipped back to the parent and re-raised there
        try:
            pickle.dumps(e)
            res = ("err", e)
        except Exception:
            res = ("err", RuntimeError(traceback.format_exc(limit=3)))
    try:
        conn.send(res)
    except Exception:
        conn.send(("mem", None))
    finally:
        conn.close()
        os._exit(0)


def run(fn, *args, mem_mb: int | None = None, timeout: float | None = None, **kwargs):
    """fn(*args) in a memory-capped child. Raises Tripped on OOM/timeout/crash; re-raises fn's own errors."""
    if not ENABLED:
        return fn(*args, **kwargs)
    limit = _clamp(_vm_bytes() + (mem_mb or MEM_MB) * 1024 * 1024)
    if limit is None:
        raise Tripped("memory")                      # no headroom under the server's own limit: refuse kindly
    if not _slots.acquire(timeout=WAIT_S):
        raise Busy()
    try:
        return _run(fn, args, kwargs, limit, timeout)
    finally:
        _slots.release()


def _run(fn, args, kwargs, limit, timeout):
    ctx = mp.get_context("fork")
    rd, wr = ctx.Pipe(duplex=False)
    p = ctx.Process(target=_child, args=(wr, fn, args, kwargs, limit), daemon=True)
    p.start()
    wr.close()
    try:
        if not rd.poll(timeout or TIMEOUT_S):
            raise Tripped("timeout")
        kind, val = rd.recv()
    except (EOFError, OSError):
        raise Tripped("crashed")
    finally:
        if p.is_alive():
            p.kill()
        p.join(5)
        rd.close()
    if kind == "mem":
        raise Tripped("memory")
    if kind == "err":
        raise val
    return val
