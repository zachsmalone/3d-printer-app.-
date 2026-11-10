"""Leave one CPU for the web process when a heavy child is running.

The production container has two CPUs. A prepare or slice that uses both of
them keeps /healthz from answering inside the proxy's health timeout, and the
proxy then answers 503 for every request.
"""
from __future__ import annotations

import os

_THREAD_KEYS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)


def leave_one_cpu() -> None:
    """Restrict this process to every CPU except one, when the machine has two or more."""
    if not hasattr(os, "sched_getaffinity"):
        return
    try:
        cpus = sorted(os.sched_getaffinity(0))
    except OSError:
        return
    if len(cpus) < 2:
        return
    try:
        os.sched_setaffinity(0, set(cpus[:-1]))
    except OSError:
        return


def single_thread_env(base: dict | None = None) -> dict:
    """Environment for a fresh interpreter. Thread pools start at 1, before NumPy is imported."""
    env = dict(os.environ if base is None else base)
    for key in _THREAD_KEYS:
        env[key] = "1"
    return env
