"""Tiny in-memory sliding-window rate limiter (single process; resets on restart).

Good enough as a brake on casual abuse (like/report spam, guessing recovery codes). It is NOT a substitute for
a proxy/WAF limiter or real accounts: restarting the server clears it and several workers would each have their own.
"""
from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_hits: dict[str, list[float]] = {}


def hit(key: str, limit: int, window_s: float, now: float | None = None) -> bool:
    """Record one event for `key`. Returns True if allowed, False if the limit for the window is already used up
    (a refused event is not recorded)."""
    t = time.time() if now is None else now
    with _lock:
        lst = [x for x in _hits.get(key, []) if t - x < window_s]
        if len(lst) >= limit:
            _hits[key] = lst
            return False
        lst.append(t)
        _hits[key] = lst
        if len(_hits) > 20000:                     # keep memory bounded
            for k in [k for k, v in _hits.items() if not v or t - v[-1] > 3600][:5000]:
                _hits.pop(k, None)
        return True


def count(key: str, window_s: float, now: float | None = None) -> int:
    t = time.time() if now is None else now
    with _lock:
        return len([x for x in _hits.get(key, []) if t - x < window_s])


def clear(key: str):
    with _lock:
        _hits.pop(key, None)


def reset():
    with _lock:
        _hits.clear()
