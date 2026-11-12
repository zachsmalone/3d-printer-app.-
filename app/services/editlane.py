"""How many CAD edits may do mesh work at once.

op, scene, slots, undo and redo run on the server's thread pool. They used to
take one of two slots and give up after 50 ms, so one person's drag — an edit,
then the scene and the slot refresh — came back "busy". /healthz is async and
does not take a place here, so a full editor lane cannot stop the probe.

A project runs one of these at a time. Further requests for that project, and
for other projects, wait in a short queue. The queue is the only place a
request waits. When it is already full the caller gets the same plain busy
message as before.
"""
from __future__ import annotations

import threading

RUNNERS = 2
QUEUE = 8
ADMIT = RUNNERS + QUEUE
LIMIT = RUNNERS
BUSY = "The editor is busy with other steps. Try again in a moment."

_state = threading.Condition()
_running_n = 0
_waiting_n = 0
_active: set[str] = set()


class Busy(Exception):
    """The editor queue is full."""


def admitted() -> int:
    """Requests running or waiting. Tests use this to see that the queue is full."""
    with _state:
        return _running_n + _waiting_n


def run(project: str, fn):
    """Run `fn` for one project. Requests for that project run one at a time."""
    global _running_n, _waiting_n
    with _state:
        if _running_n + _waiting_n >= ADMIT:
            raise Busy()
        _waiting_n += 1
        while _running_n >= RUNNERS or (project is not None and project in _active):
            _state.wait()
        _waiting_n -= 1
        _running_n += 1
        if project is not None:
            _active.add(project)
    try:
        return fn()
    finally:
        with _state:
            _running_n -= 1
            if project is not None:
                _active.discard(project)
            _state.notify_all()
