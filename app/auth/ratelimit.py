"""Sliding-window rate limits kept in SQLite (shared by all server workers, survive restarts)."""
from __future__ import annotations

import math
from typing import Callable

from app.auth.errors import RateLimited
from app.auth.store import AuthStore

_KEEP_S = 86400


class RateLimiter:
    def __init__(self, store: AuthStore, clock: Callable[[], float]):
        self.store, self.clock = store, clock

    def blocked(self, key: str, limit: tuple) -> int:
        """Seconds until allowed again, or 0 if under the limit. Does not record anything."""
        max_events, window = limit
        now = self.clock()
        row = self.store.one("SELECT COUNT(*) AS n, MIN(ts) AS oldest FROM rate_events WHERE key=? AND ts>?",
                             (key, now - window))
        if row["n"] >= max_events:
            return max(1, math.ceil(row["oldest"] + window - now))
        return 0

    def record(self, key: str) -> None:
        now = self.clock()
        self.store.run("INSERT INTO rate_events(key, ts) VALUES(?, ?)", (key, now))
        self.store.run("DELETE FROM rate_events WHERE ts<?", (now - _KEEP_S,))

    def hit(self, key: str, limit: tuple) -> None:
        """Count this attempt and raise RateLimited if it exceeds the limit (atomic)."""
        with self.store.tx():
            wait = self.blocked(key, limit)
            if wait:
                raise RateLimited(wait)
            self.record(key)

    def check(self, key: str, limit: tuple) -> None:
        """Raise RateLimited if already over the limit (used for failure-only counters)."""
        wait = self.blocked(key, limit)
        if wait:
            raise RateLimited(wait)
