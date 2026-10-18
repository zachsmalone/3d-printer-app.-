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
import traceback

MEM_MB = int(os.environ.get("PHOTO3D_HEAVY_MEM_MB", "1500"))     # extra address space on top of the parent's
TIMEOUT_S = float(os.environ.get("PHOTO3D_HEAVY_TIMEOUT_S", "120"))
ENABLED = os.environ.get("PHOTO3D_HEAVY_GUARD", "1") != "0"


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


def _child(conn, fn, args, kwargs, limit):
    try:
        if limit:
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
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
    limit = _vm_bytes() + (mem_mb or MEM_MB) * 1024 * 1024
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
