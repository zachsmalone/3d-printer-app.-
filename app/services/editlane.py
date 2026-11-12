"""How many CAD edits may do mesh work at once.

op, scene, slots, undo and redo are synchronous and used to run on the shared
thread pool. A drag that also rebuilt the scene filled that pool, and a heavy
step used to fork the server while those threads were inside NumPy. /healthz
is async and does not take a slot here, so a full editor lane cannot stop the
probe. Extra edits get a short "busy" instead of waiting on the pool.
"""
from __future__ import annotations

import threading

LIMIT = 2
WAIT_S = 0.05
BUSY = "The editor is busy with other steps. Try again in a moment."
_slots = threading.BoundedSemaphore(LIMIT)


class Busy(Exception):
    """Both editor slots are taken."""


def run(fn):
    if not _slots.acquire(timeout=WAIT_S):
        raise Busy()
    try:
        return fn()
    finally:
        _slots.release()
