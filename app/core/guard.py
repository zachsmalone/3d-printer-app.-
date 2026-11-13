"""Runtime ceiling for heavy geometry work (CADRT-1 / QA B1 / B4).

Pre-flight estimates can be wrong, so heavy ops run outside the server with a hard
address-space limit (RLIMIT_AS) and a wall-clock timeout. If that process runs out of memory,
crashes or times out, the caller gets a friendly error and nothing in the server (the scene,
the project) has changed.

The server must not os.fork() for this. It is a multi-threaded process and NumPy's OpenBLAS
pool is already running. Python 3.12 stops every thread before fork; a thread inside OpenBLAS
does not stop, and the whole interpreter waits forever. /healthz is on that interpreter, so
the probe times out and the proxy takes the site down.

The usual path is a small pool of long-lived workers started with the spawn method
(app/core/guardpool.py). They import NumPy and trimesh once. A one-shot interpreter is
only the fallback when a warm worker cannot take the address cap (a tight ulimit).
Neither path copies the listening socket, the locks, or the server's threads.
"""
from __future__ import annotations

import importlib
import json
import marshal
import os
import pickle
import resource
import subprocess
import sys
import tempfile
import threading
import traceback
import types
from pathlib import Path

from app.core import affinity, guardpool

MEM_MB = int(os.environ.get("PHOTO3D_HEAVY_MEM_MB", "1500"))     # budget on top of the server's address size (N3)
# Tests set this in the server process. A forked copy would still see it; a fresh interpreter does not.
_inherited_mark = None
ROOT = Path(__file__).resolve().parents[2]
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
    Returns the limit, or None when the hard limit leaves no usable headroom (refuse kindly, no process).

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


def _pack_fn(fn):
    """Ship `fn` to a fresh interpreter.

    Functions on `app.*` pickle by import path. A test helper or a function typed into
    `python -c` does not (pytest loads that file under a name the fresh interpreter cannot
    import), so its code is sent instead.
    """
    mod = getattr(fn, "__module__", "") or ""
    if mod == "builtins" or mod.startswith("app.") or mod.startswith("numpy"):
        try:
            return ("pickle", pickle.dumps(fn, protocol=pickle.HIGHEST_PROTOCOL))
        except Exception:
            pass
    if getattr(fn, "__closure__", None):
        raise TypeError(f"{getattr(fn, '__name__', fn)} cannot run outside this process")
    globs = {}
    for name in fn.__code__.co_names:
        if name not in fn.__globals__:
            continue
        val = fn.__globals__[name]
        if isinstance(val, types.ModuleType):
            globs[name] = ("mod", val.__name__)
            continue
        try:
            globs[name] = ("val", pickle.dumps(val, protocol=pickle.HIGHEST_PROTOCOL))
        except Exception:
            continue
    return ("code", marshal.dumps(fn.__code__), fn.__name__, fn.__defaults__, globs)


def _unpack_fn(packed):
    kind = packed[0]
    if kind == "pickle":
        return pickle.loads(packed[1])
    _kind, code_b, name, defaults, globs = packed
    ns: dict = {"__builtins__": __builtins__}
    for gname, spec in globs.items():
        if spec[0] == "mod":
            ns[gname] = importlib.import_module(spec[1])
        else:
            ns[gname] = pickle.loads(spec[1])
    return types.FunctionType(marshal.loads(code_b), ns, name, defaults)


def _apply_limit(limit: int) -> None:
    if not limit:
        return
    _soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    cap = limit if hard in (resource.RLIM_INFINITY, -1) else min(limit, hard)
    try:
        resource.setrlimit(resource.RLIMIT_AS, (cap, hard if hard not in (resource.RLIM_INFINITY, -1) else cap))
    except (ValueError, OSError):
        pass


def _note_spawn(report: str) -> None:
    """Record whether this process inherited the server's Python heap. Unset in production."""
    if not report:
        return
    try:
        folder = Path(report)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{os.getpid()}.json").write_text(
            json.dumps({"pid": os.getpid(), "spawn_mark": _inherited_mark}),
            encoding="utf-8",
        )
    except OSError:
        pass


def _child_main(src: str, dst: str) -> None:
    request = pickle.loads(Path(src).read_bytes())
    _note_spawn(os.environ.get("ZEIM_GUARD_REPORT", ""))
    fn = _unpack_fn(request["fn"])
    _apply_limit(int(request.get("limit") or 0))
    try:
        result = ("ok", fn(*request["args"], **request.get("kwargs") or {}))
    except MemoryError:
        result = ("mem", None)
    except BaseException as exc:  # noqa: BLE001 - shipped back to the server and re-raised there
        if type(exc).__name__ == "RTreeError" or "bad_alloc" in str(exc).lower():
            result = ("mem", None)
        else:
            try:
                pickle.dumps(exc)
                result = ("err", exc)
            except Exception:
                result = ("err", RuntimeError(traceback.format_exc(limit=3)))
    Path(dst).write_bytes(pickle.dumps(result, protocol=pickle.HIGHEST_PROTOCOL))


def warm() -> None:
    """Start the mesh workers and import their libraries. No-op when the guard is off."""
    if not ENABLED or os.environ.get("ZEIM_GUARD_WORKER") == "1":
        return
    guardpool.ensure(MAX_CHILDREN)
    guardpool.warm()


def worker_pids() -> list[int]:
    return guardpool.worker_pids()


def run(fn, *args, mem_mb: int | None = None, timeout: float | None = None, **kwargs):
    """fn(*args) in a memory-capped process. Raises Tripped on OOM/timeout/crash; re-raises fn's own errors.

    A worker that is itself already inside this guard runs the call directly. Spawning
    another interpreter from there would nest the cap and can deadlock the pool.
    """
    if os.environ.get("ZEIM_GUARD_WORKER") == "1" or not ENABLED:
        return fn(*args, **kwargs)
    limit = _clamp(_vm_bytes() + (mem_mb or MEM_MB) * 1024 * 1024)
    if limit is None:
        raise Tripped("memory")                      # no headroom under the server's own limit: refuse kindly
    if not _slots.acquire(timeout=WAIT_S):
        raise Busy()
    try:
        guardpool.ensure(MAX_CHILDREN)
        try:
            return guardpool.call(_pack_fn(fn), args, kwargs, limit, timeout or TIMEOUT_S)
        except guardpool.Down:
            return _run(fn, args, kwargs, limit, timeout)
        except guardpool.Failed as exc:
            # The warm worker's imports do not fit this cap. A one-shot interpreter is smaller.
            if exc.kind == "fresh":
                return _run(fn, args, kwargs, limit, timeout)
            if exc.kind == "err":
                raise exc.value
            raise Tripped(exc.kind)
    finally:
        _slots.release()


def _run(fn, args, kwargs, limit, timeout):
    request = {"fn": _pack_fn(fn), "args": args, "kwargs": kwargs, "limit": limit}
    with tempfile.TemporaryDirectory(prefix="zeim-guard-") as folder:
        folder_path = Path(folder)
        src = folder_path / "in.pickle"
        dst = folder_path / "out.pickle"
        src.write_bytes(pickle.dumps(request, protocol=pickle.HIGHEST_PROTOCOL))
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "app.core.guard", str(src), str(dst)],
                cwd=str(ROOT),
                env=affinity.single_thread_env(),
                capture_output=True,
                timeout=timeout or TIMEOUT_S,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise Tripped("timeout")
        if not dst.is_file():
            raise Tripped("memory" if proc.returncode < 0 else "crashed")
        try:
            kind, val = pickle.loads(dst.read_bytes())
        except (OSError, pickle.UnpicklingError, EOFError):
            raise Tripped("crashed")
    if kind == "mem":
        raise Tripped("memory")
    if kind == "err":
        raise val
    if kind == "ok":
        return val
    raise Tripped("crashed")


if __name__ == "__main__":
    _child_main(sys.argv[1], sys.argv[2])
