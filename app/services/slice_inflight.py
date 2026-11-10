"""One FDM slice at a time for the same user and job.

The global slicer slot allows two slices at once. A second request for a job
that is already slicing used to take the other slot and return 200, which the
page treated as a finished slice. Callers turn SliceBusy into HTTP 409.
"""
from __future__ import annotations

import threading

BUSY_MESSAGE = "This slice is still working. Wait for it to finish."

_lock = threading.Lock()
_running: set[tuple[str, str]] = set()


class SliceBusy(Exception):
    """This user already has this job in a slice."""


def claim(sid: str, job: str) -> None:
    """Reserve (sid, job). An empty sid or job is not a slice identity and is ignored."""
    if not sid or not job:
        return
    key = (str(sid), str(job))
    with _lock:
        if key in _running:
            raise SliceBusy()
        _running.add(key)


def release(sid: str, job: str) -> None:
    if not sid or not job:
        return
    with _lock:
        _running.discard((str(sid), str(job)))


def reset() -> None:
    """Test helper. Production slices release themselves."""
    with _lock:
        _running.clear()
