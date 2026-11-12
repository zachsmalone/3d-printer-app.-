"""CPU sharing between a heavy child and the web process.

The production container has two CPUs. A prepare that is pinned to one of them
with a single BLAS thread misses the 240 s limit on a detailed shell. The
prepare child may use both, at a lower priority, so a /healthz probe (normal
priority) still runs. Slice programs keep leaving one CPU free: they call
`leave_one_cpu` themselves.
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

# Two BLAS/OpenMP threads. The libraries that release the GIL (distance
# transforms, marching cubes, the simplifier) can use the second CPU.
PREPARE_THREADS = 2


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


def take_compute_cpus(max_cpus: int = PREPARE_THREADS) -> None:
    """Use up to `max_cpus` at a lower priority than the web process.

    When the machine is idle the child still gets the cores. When /healthz
    runs, the normal-priority server preempts this child.
    """
    try:
        os.nice(10)
    except OSError:
        pass
    if not hasattr(os, "sched_getaffinity"):
        return
    try:
        cpus = sorted(os.sched_getaffinity(0))
    except OSError:
        return
    if len(cpus) <= max_cpus:
        return
    try:
        os.sched_setaffinity(0, set(cpus[:max_cpus]))
    except OSError:
        return


def job_env(threads: int = PREPARE_THREADS, base: dict | None = None) -> dict:
    """Environment for a fresh interpreter. Set before NumPy is imported."""
    env = dict(os.environ if base is None else base)
    for key in _THREAD_KEYS:
        env[key] = str(max(1, int(threads)))
    return env


def single_thread_env(base: dict | None = None) -> dict:
    """One thread. Slice helpers that must not take the second CPU use this."""
    return job_env(1, base)
