"""Warm workers for heavy mesh steps.

The web process must not os.fork(). Python 3.12 stops every thread for that fork
and waits forever on an OpenBLAS thread, so /healthz never runs. Each worker
here is started with the spawn start method: a fresh interpreter, with none of
the server's threads, locks, or listening socket. NumPy, trimesh, and the mesh
ops are imported once when the worker starts. Later steps only do the geometry.

A task still has the same address-space cap and wall-clock timeout as a one-shot
interpreter. On timeout the worker is killed and a new one is spawned. A worker
is also replaced after a fixed number of tasks, or when its resident set has
grown, so a leak does not accumulate.

Meshes are not pickled. Vertex and face arrays are written as raw bytes on
tmpfs (/dev/shm when it is available) and the worker reads them back.
"""
from __future__ import annotations

import atexit
import logging
import multiprocessing as mp
import os
import pickle
import resource
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

log = logging.getLogger("zeim.guard")

_BOOTING = object()
_lock = threading.Lock()
_pool: list = []
_started_ok = False
_UNSET = object()
_fail_hard: int | None | object = _UNSET
_LIBS = None
_stopped = False

# Replaced after this many tasks, or after resident memory grows by this much.
# Read on each task so a test can tighten them without restarting the process.
def _task_budget() -> int:
    try:
        return max(1, int(os.environ.get("PHOTO3D_HEAVY_TASKS", "32")))
    except ValueError:
        return 32


def _growth_budget() -> int:
    try:
        mb = max(1, int(os.environ.get("PHOTO3D_HEAVY_GROWTH_MB", "256")))
    except ValueError:
        mb = 256
    return mb * 1024 * 1024


class Down(Exception):
    """No warm worker can start. The caller runs a one-shot interpreter instead."""


class Failed(Exception):
    """The task ended in the worker. `kind` is timeout, memory, crashed, fresh, or err."""

    def __init__(self, kind: str, value=None):
        super().__init__(kind)
        self.kind = kind
        self.value = value


class _Proc:
    def __init__(self, proc, conn):
        self.proc = proc
        self.conn = conn
        self.busy = False


def ensure(n: int) -> None:
    """Grow or shrink the slot list to `n` workers. Does not start them."""
    global _pool
    n = max(1, int(n))
    with _lock:
        if len(_pool) == n:
            return
        if len(_pool) > n:
            extra = _pool[n:]
            del _pool[n:]
        else:
            extra = []
            _pool.extend([None] * (n - len(_pool)))
    for slot in extra:
        if _alive(slot):
            _drop(slot)


def warm() -> None:
    """Start every worker and wait until its libraries are imported."""
    if _stopped:
        return
    for i in range(len(_pool)):
        with _lock:
            slot = _pool[i] if i < len(_pool) else None
            if _alive(slot) or slot is _BOOTING:
                continue
            if i >= len(_pool):
                return
            _pool[i] = _BOOTING
        proc = _boot()
        with _lock:
            if i < len(_pool) and _pool[i] is _BOOTING:
                _pool[i] = proc


def worker_pids() -> list[int]:
    with _lock:
        return [slot.proc.pid for slot in _pool if _alive(slot)]


def call(packed_fn, args, kwargs, limit: int, timeout: float):
    """Run one packed call. Raises Down or Failed. Does not raise the task's own error."""
    if _stopped:
        raise Down()
    root = _tmp_root()
    with tempfile.TemporaryDirectory(prefix="zeim-mesh-", dir=root) as folder:
        counter = [0]
        request = {
            "fn": packed_fn,
            "args": _export(args, folder, counter, "p"),
            "kwargs": _export(kwargs, folder, counter, "p"),
            "limit": int(limit or 0),
            "dir": folder,
            "report": os.environ.get("ZEIM_GUARD_REPORT", ""),
            "task_budget": _task_budget(),
            "growth_budget": _growth_budget(),
        }
        fresh = 0
        while fresh < 2:
            worker = _checkout()
            if worker is None:
                if fresh:
                    raise Failed("fresh")
                raise Down() if not _started_ok else Failed("crashed")
            try:
                msg = _exchange(worker, request, timeout)
            except Failed as exc:
                _replace(worker)
                raise exc
            kind = msg.get("kind")
            if kind == "fresh":
                fresh += 1
                _replace(worker)
                continue
            if kind == "ok":
                try:
                    value = _realize(msg.get("value"), folder)
                except Exception:
                    _replace(worker)
                    raise Failed("crashed")
                if msg.get("retire") or not _alive(worker):
                    _replace(worker)
                else:
                    _checkin(worker)
                return value
            if kind == "err":
                _checkin(worker)
                raise Failed("err", msg.get("value"))
            _replace(worker)
            if kind == "mem":
                raise Failed("memory")
            raise Failed(kind or "crashed")
        raise Failed("fresh")


def _checkout():
    idx = None
    with _lock:
        for slot in _pool:
            if _alive(slot) and not slot.busy:
                slot.busy = True
                return slot
        if not _boot_allowed():
            return None
        for i, slot in enumerate(_pool):
            if slot is _BOOTING:
                continue
            if slot is None or not _alive(slot):
                _pool[i] = _BOOTING
                idx = i
                break
    if idx is None:
        return None
    proc = _boot()
    with _lock:
        if idx < len(_pool) and _pool[idx] is _BOOTING:
            _pool[idx] = proc
        elif _alive(proc):
            _drop(proc)
            proc = None
    if proc is None:
        return None
    proc.busy = True
    return proc


def _checkin(worker) -> None:
    with _lock:
        if _alive(worker):
            worker.busy = False


def _replace(worker) -> None:
    idx = None
    with _lock:
        for i, slot in enumerate(_pool):
            if slot is worker:
                _pool[i] = _BOOTING
                idx = i
                break
    _drop(worker)
    if idx is None or not _boot_allowed():
        with _lock:
            if idx is not None and idx < len(_pool) and _pool[idx] is _BOOTING:
                _pool[idx] = None
        return
    proc = _boot()
    with _lock:
        if idx < len(_pool) and _pool[idx] is _BOOTING:
            _pool[idx] = proc


def _alive(slot) -> bool:
    return isinstance(slot, _Proc) and slot.proc.is_alive()


def _drop(worker) -> None:
    if not isinstance(worker, _Proc):
        return
    try:
        if worker.proc.is_alive():
            worker.proc.kill()
        worker.proc.join(5)
    except OSError:
        pass
    try:
        worker.conn.close()
    except OSError:
        pass


def _hard_cap() -> int | None:
    _soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    if hard in (resource.RLIM_INFINITY, -1):
        return None
    return hard


def _boot_allowed() -> bool:
    """Skip a new worker when one already died under this same hard address cap.

    A tight `ulimit -v` can kill the worker while it imports. A one-shot
    interpreter imports less and still fits. A larger cap tries the pool again.
    """
    if _fail_hard is _UNSET:
        return True
    hard = _hard_cap()
    if hard is None:
        return True
    if _fail_hard is None:
        return True
    return hard > _fail_hard


def _spawn_main_ok() -> bool:
    """Spawn re-imports __main__. `python -c` has nothing to re-import, so the pool cannot start.

    Those callers use the one-shot interpreter. A normal server or test run has a real file.
    """
    path = getattr(sys.modules.get("__main__"), "__file__", None)
    return bool(path) and os.path.isfile(path)


def _boot():
    global _started_ok, _fail_hard
    if not _boot_allowed() or not _spawn_main_ok():
        return None
    ctx = mp.get_context("spawn")
    parent, child = ctx.Pipe(duplex=True)
    proc = ctx.Process(target=_worker_main, args=(child,), daemon=True, name="zeim-mesh")
    try:
        proc.start()
    except OSError:
        log.warning("mesh worker did not start", exc_info=True)
        parent.close()
        child.close()
        return None
    child.close()
    deadline = time.monotonic() + 60
    ready = None
    while time.monotonic() < deadline:
        if parent.poll(0.2):
            try:
                ready = parent.recv()
            except (EOFError, OSError):
                ready = None
            break
        if not proc.is_alive():
            break
    if not ready or not ready.get("ready") or not proc.is_alive():
        err = (ready or {}).get("err")
        if err:
            log.warning("mesh worker failed during import: %s", err[-600:])
        else:
            log.warning("mesh worker exited before it was ready (hard cap %s)", _hard_cap())
        if _hard_cap() is not None:
            _fail_hard = _hard_cap()
        try:
            if proc.is_alive():
                proc.kill()
            proc.join(3)
        except OSError:
            pass
        parent.close()
        return None
    _started_ok = True
    _fail_hard = _UNSET
    return _Proc(proc, parent)


def _exchange(worker, request, timeout: float):
    try:
        worker.conn.send(request)
    except (BrokenPipeError, EOFError, OSError):
        raise Failed("crashed")
    try:
        if not worker.conn.poll(timeout):
            raise Failed("timeout")
        return worker.conn.recv()
    except Failed:
        raise
    except (EOFError, OSError):
        code = worker.proc.exitcode
        raise Failed("memory" if code is not None and code < 0 else "crashed")


def _tmp_root() -> str | None:
    shm = Path("/dev/shm")
    if shm.is_dir() and os.access(shm, os.W_OK):
        return str(shm)
    return None


def _stop() -> None:
    global _stopped
    _stopped = True
    with _lock:
        slots = list(_pool)
        for i in range(len(_pool)):
            _pool[i] = None
    for slot in slots:
        if isinstance(slot, _Proc):
            _drop(slot)


atexit.register(_stop)


# ---------------------------------------------------------------- arrays on tmpfs
def _is_mesh(obj) -> bool:
    kind = type(obj)
    return kind.__name__ == "Trimesh" and str(kind.__module__).startswith("trimesh")


def _is_array(obj) -> bool:
    kind = type(obj)
    mod = str(kind.__module__)
    if mod != "numpy" and not mod.startswith("numpy.") and not mod.startswith("trimesh"):
        return False
    dtype = getattr(obj, "dtype", None)
    if dtype is None or getattr(dtype, "kind", "O") == "O":
        return False
    return hasattr(obj, "tobytes") and hasattr(obj, "shape") and hasattr(obj, "nbytes")


def _write_raw(folder: str, prefix: str, counter: list, raw: bytes) -> str:
    name = f"{prefix}{counter[0]:04d}.bin"
    counter[0] += 1
    path = Path(folder) / name
    path.write_bytes(raw)
    return name


def _array_spec(obj, folder: str, counter: list, prefix: str) -> dict:
    raw = obj.tobytes()
    return {
        "__zeim__": "bin",
        "name": _write_raw(folder, prefix, counter, raw),
        "shape": [int(n) for n in obj.shape],
        "dtype": obj.dtype.str,
    }


def _export(obj, folder: str, counter: list, prefix: str, depth: int = 0):
    """Replace meshes and large arrays with tmpfs file specs. Leave small values inline."""
    if depth > 8:
        return obj
    if _is_mesh(obj):
        faces = obj.faces
        verts = obj.vertices
        attrs = {}
        table = getattr(obj, "face_attributes", None)
        if table is not None:
            try:
                items = list(table.items())
            except Exception:
                items = []
            for key, val in items:
                if _is_array(val):
                    attrs[str(key)] = _array_spec(val, folder, counter, prefix)
        return {
            "__zeim__": "mesh",
            "v": _array_spec(verts, folder, counter, prefix),
            "f": _array_spec(faces, folder, counter, prefix),
            "fa": attrs,
        }
    if _is_array(obj) and int(obj.nbytes) >= 65536:
        return _array_spec(obj, folder, counter, prefix)
    if isinstance(obj, (bytes, bytearray)) and len(obj) >= 65536:
        return {"__zeim__": "bytes", "name": _write_raw(folder, prefix, counter, bytes(obj))}
    if isinstance(obj, dict):
        return {k: _export(v, folder, counter, prefix, depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_export(v, folder, counter, prefix, depth + 1) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_export(v, folder, counter, prefix, depth + 1) for v in obj)
    return obj


def _libs():
    """NumPy and trimesh. The worker sets this at startup, after the thread cap.

    Imported here only when a result actually contains an array, so importing
    this module does not start OpenBLAS in the one-shot interpreter.
    """
    global _LIBS
    if _LIBS is None:
        import numpy as np
        import trimesh
        _LIBS = (np, trimesh)
    return _LIBS


def _read_array(folder: str, spec: dict, np):
    path = Path(folder) / spec["name"]
    if path.parent != Path(folder):
        raise Failed("crashed")
    raw = path.read_bytes()
    shape = tuple(int(n) for n in spec["shape"])
    dtype = np.dtype(spec["dtype"])
    if not raw:
        return np.zeros(shape, dtype)
    return np.frombuffer(raw, dtype=dtype).reshape(shape).copy()


def _realize(obj, folder: str, depth: int = 0):
    if depth > 8:
        return obj
    if isinstance(obj, dict):
        kind = obj.get("__zeim__")
        if kind == "mesh":
            np, trimesh = _libs()
            mesh = trimesh.Trimesh(
                _read_array(folder, obj["v"], np),
                _read_array(folder, obj["f"], np),
                process=False,
            )
            for key, spec in (obj.get("fa") or {}).items():
                mesh.face_attributes[str(key)] = _read_array(folder, spec, np)
            return mesh
        if kind == "bin":
            np, _trimesh = _libs()
            return _read_array(folder, obj, np)
        if kind == "bytes":
            path = Path(folder) / obj["name"]
            if path.parent != Path(folder):
                raise Failed("crashed")
            return path.read_bytes()
        return {k: _realize(v, folder, depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_realize(v, folder, depth + 1) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_realize(v, folder, depth + 1) for v in obj)
    return obj


def _set_one_thread() -> None:
    # Before NumPy is imported. OpenBLAS reads these at startup and will not
    # shrink a pool it has already created.
    for key in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        os.environ[key] = "1"


def _rss() -> int:
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        pass
    return 0


def _worker_main(conn) -> None:
    """Fresh interpreter. Libraries load once; each message is one guarded task."""
    os.environ["ZEIM_GUARD_WORKER"] = "1"
    _set_one_thread()
    try:
        # Imported after the thread cap. A fork of the server would already
        # have these loaded and would see the server's guard mark.
        import numpy as np
        import trimesh
        import app.core.meshedit  # noqa: F401  warm translate / booleans / sculpt
        import app.core.cadops  # noqa: F401
        global _LIBS
        _LIBS = (np, trimesh)
        from app.core import guard
    except Exception:
        try:
            conn.send({"ready": False, "err": traceback.format_exc()})
        except Exception:
            pass
        return
    born = _rss()
    tasks = 0
    try:
        conn.send({"ready": True, "pid": os.getpid(), "rss": born})
        while True:
            request = conn.recv()
            if request is None:
                break
            guard._note_spawn(request.get("report") or "")
            limit = int(request.get("limit") or 0)
            vm = guard._vm_bytes()
            if limit and limit - vm < guard.MIN_HEADROOM:
                conn.send({"kind": "fresh"})
                break
            guard._apply_limit(limit)
            try:
                fn = guard._unpack_fn(request["fn"])
                args = _realize(request.get("args"), request["dir"])
                kwargs = _realize(request.get("kwargs"), request["dir"])
                if not isinstance(kwargs, dict):
                    kwargs = {}
                result = fn(*args, **kwargs)
                tasks += 1
                grown = _rss() - born
                budget = int(request.get("growth_budget") or (256 * 1024 * 1024))
                retire = tasks >= int(request.get("task_budget") or 32) or grown >= budget
                conn.send({
                    "kind": "ok",
                    "value": _export(result, request["dir"], [0], "w"),
                    "retire": retire,
                })
                if retire:
                    break
            except MemoryError:
                conn.send({"kind": "mem"})
                break
            except BaseException as exc:  # noqa: BLE001 - shipped to the server and re-raised there
                if type(exc).__name__ == "RTreeError" or "bad_alloc" in str(exc).lower():
                    conn.send({"kind": "mem"})
                    break
                try:
                    pickle.dumps(exc)
                    conn.send({"kind": "err", "value": exc})
                except Exception:
                    conn.send({"kind": "err", "value": RuntimeError(traceback.format_exc(limit=3))})
    except (EOFError, BrokenPipeError, OSError):
        return
    finally:
        try:
            conn.close()
        except OSError:
            pass
