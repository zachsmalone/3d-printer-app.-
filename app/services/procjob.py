"""Run one heavy call in a fresh interpreter.

Forking the web process (core/guard.py) copies the listening socket, the
thread locks, and the server heap. A long resin prepare then stalls the
parent: /healthz misses the proxy timeout and every request comes back 503.
A new interpreter does not inherit that state. The parent only waits.
"""
from __future__ import annotations

import importlib
import logging
import os
import pickle
import resource
import subprocess
import sys
import tempfile
from pathlib import Path

from app.core import affinity
from app.core.guard import Tripped

log = logging.getLogger("zeim.procjob")
ROOT = Path(__file__).resolve().parents[2]


def _vm_bytes() -> int:
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith("VmSize:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        pass
    return 0


def _apply_memory(mem_mb: int) -> None:
    """Let this fresh process grow by mem_mb from the size it has after import."""
    if mem_mb <= 0:
        return
    want = _vm_bytes() + mem_mb * 1024 * 1024
    _soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    if hard not in (resource.RLIM_INFINITY, -1):
        want = min(want, hard)
    try:
        resource.setrlimit(resource.RLIMIT_AS, (want, hard if hard not in (resource.RLIM_INFINITY, -1) else want))
    except (ValueError, OSError):
        pass


def call(fn, args: tuple, *, timeout: float, mem_mb: int):
    """fn(*args) in a child process. Re-raises fn's exception. Tripped on timeout, crash, or memory."""
    request = {"module": fn.__module__, "name": fn.__name__, "args": args, "mem_mb": mem_mb}
    with tempfile.TemporaryDirectory(prefix="zeim-job-") as folder:
        folder_path = Path(folder)
        src = folder_path / "in.pickle"
        dst = folder_path / "out.pickle"
        src.write_bytes(pickle.dumps(request, protocol=pickle.HIGHEST_PROTOCOL))
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "app.services.procjob", str(src), str(dst)],
                cwd=str(ROOT),
                env=affinity.single_thread_env(),
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise Tripped("timeout")
        if not dst.is_file():
            tail = (proc.stderr or b"").decode("utf-8", "replace")[-400:]
            log.error("heavy job produced no result rc=%s: %s", proc.returncode, tail)
            raise Tripped("memory" if proc.returncode < 0 else "crashed")
        try:
            kind, val = pickle.loads(dst.read_bytes())
        except (OSError, pickle.UnpicklingError, EOFError):
            raise Tripped("crashed")
    if kind == "ok":
        return val
    if kind == "mem":
        raise Tripped("memory")
    if kind == "err":
        raise val
    raise Tripped("crashed")


def _child(src: str, dst: str) -> None:
    affinity.leave_one_cpu()
    request = pickle.loads(Path(src).read_bytes())
    try:
        # Import before the cap. A fresh interpreter's libraries reserve address space
        # that must not count against the job's own budget.
        mod = importlib.import_module(request["module"])
        _apply_memory(int(request.get("mem_mb") or 0))
        fn = getattr(mod, request["name"])
        result = ("ok", fn(*request["args"]))
    except MemoryError:
        result = ("mem", None)
    except BaseException as exc:  # noqa: BLE001 - shipped back to the parent and re-raised there
        # libspatialindex raises RTreeError(std::bad_alloc) instead of MemoryError
        # when the address-space cap is hit. Treat that like the memory trip so
        # /prepare can return the same 422 tip as a killed child.
        if type(exc).__name__ == "RTreeError" or "bad_alloc" in str(exc).lower():
            result = ("mem", None)
        else:
            try:
                pickle.dumps(exc)
                result = ("err", exc)
            except Exception:
                result = ("err", RuntimeError(type(exc).__name__))
    Path(dst).write_bytes(pickle.dumps(result, protocol=pickle.HIGHEST_PROTOCOL))


if __name__ == "__main__":
    _child(sys.argv[1], sys.argv[2])
