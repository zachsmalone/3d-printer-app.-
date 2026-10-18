"""Slicing activity counters for the admin metrics endpoint (synchronous design: there is no
queue, so 'running/failed' is the honest shape — totals + failures + last error)."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from .. import config

_LOCK = threading.Lock()


def _path() -> Path:
    return Path(config.DATA) / "slice_stats.json"


def record(ok: bool, error: str = "") -> None:
    with _LOCK:
        try:
            d = json.loads(_path().read_text())
        except Exception:
            d = {"total": 0, "failures": 0}
        d["total"] += 1
        d["last_at"] = time.time()
        if not ok:
            d["failures"] += 1
            d["last_error"] = error[:200]
            d["last_failure_at"] = time.time()
        _path().parent.mkdir(parents=True, exist_ok=True)
        _path().write_text(json.dumps(d))


def snapshot() -> dict:
    with _LOCK:
        try:
            return json.loads(_path().read_text())
        except Exception:
            return {"total": 0, "failures": 0}
