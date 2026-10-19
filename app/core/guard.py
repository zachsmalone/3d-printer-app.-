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

MEM_MB = int(os.environ.get("PHOTO3D_HEAVY_MEM_MB", "1500"))     # per-child budget on top of what it inherits at fork (N3)
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


def _hard_cap() -> int | None:
    """The inherited HARD RLIMIT_AS, or None when there is none. No unprivileged process can raise it (CADRT-8)."""
    _soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    return None if hard in (resource.RLIM_INFINITY, -1) else hard


def _clamp(want: int) -> int | None:
    """The child's address-space limit for `want` bytes (= what it inherits at fork + its budget), never above the
    inherited HARD limit, so setrlimit can never fail with "not allowed to raise maximum limit" (CADRT-8).
    Returns the limit, or None when the hard limit leaves no usable headroom (refuse kindly, no fork).

    N3: the budget no longer depends on what is left under the server's SOFT limit. A long-running server's
    VmSize grows with reserved-but-untouched address space (malloc arenas, thread stacks, freed-but-mapped
    pools) that it never gives back, so "soft cap minus parent VmSize" shrank until even a 20k-face print check
    could not run. RLIMIT_AS is per process: setting the child's soft limit (up to hard, which the kernel always
    allows) gives the server process itself no extra room, and the child can still add at most its budget."""
    hard = _hard_cap()
    limit = want if hard is None else min(want, hard)
    if limit - _vm_bytes() < MIN_HEADROOM:
        return None
    return limit


def _child(conn, fn, args, kwargs, limit):
    try:
        if limit:
            try:
                soft, hard = resource.getrlimit(resource.RLIMIT_AS)
                resource.setrlimit(resource.RLIMIT_AS, (limit, hard))
            except (ValueError, OSError):
                pass                                   # keep the inherited limit
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
