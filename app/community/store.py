"""Tiny locked JSON file store (stand-in for a database)."""
from __future__ import annotations

import json
import threading
from pathlib import Path

from ..config import DATA

_lock = threading.RLock()


class JsonFile:
    def __init__(self, name: str, default):
        self.path: Path = DATA / name
        self.default = default

    def read(self):
        with _lock:
            if self.path.exists():
                try:
                    return json.loads(self.path.read_text())
                except Exception:
                    pass
            return json.loads(json.dumps(self.default))

    def write(self, data):
        with _lock:
            self.path.write_text(json.dumps(data, indent=1, default=str))

    def update(self, fn):
        with _lock:
            d = self.read()
            r = fn(d)
            self.write(d)
            return r


USERS = JsonFile("users.json", {})          # sid -> account (DOB, flags)
PREFS = JsonFile("prefs.json", {})          # sid -> personalization data
LISTINGS = JsonFile("projects.json", [])    # user-published (free) projects
MODERATION = JsonFile("moderation.json", {"hidden": [], "reports": []})
CLASSROOMS = JsonFile("classrooms.json", {})  # code -> classroom
PROGRESS = JsonFile("education_progress.json", {})
ENGAGEMENT = JsonFile("engagement.json", {"likes": {}, "downloads": {}})   # item id -> [visitor sids] (one each)
AGE_BLOCKS = JsonFile("age_blocks.json", {})   # sha256(sid)[:24] -> unix time the lock ends (no DOB, no age is ever stored here)
