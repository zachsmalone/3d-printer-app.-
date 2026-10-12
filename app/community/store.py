"""Tiny locked JSON file store (stand-in for a database)."""
from __future__ import annotations

import json
import os
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
        """Atomic (temp file + rename) and private: only the account that runs the server can read these files (mode 600)."""
        with _lock:
            tmp = self.path.with_name(self.path.name + ".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as fh:
                fh.write(json.dumps(data, indent=1, default=str))
            os.replace(tmp, self.path)

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
# 2026-10-12: school features removed. A pre-existing data/classrooms.json (and data/classroom_projects/) is no longer
# read or written by any code; it is left on disk untouched (no deletion of existing data). Owner decides on cleanup.
PROGRESS = JsonFile("education_progress.json", {})
ENGAGEMENT = JsonFile("engagement.json", {"likes": {}, "downloads": {}})   # item id -> [visitor sids] (one each)
AGE_BLOCKS = JsonFile("age_blocks.json", {})   # sha256(sid)[:24] -> unix time the lock ends (no DOB, no age is ever stored here)
# Community features (Oct 2026): favorites, timestamped activity for Trending, "I printed this" photos
FAVORITES = JsonFile("favorites.json", {})      # sid -> [item ids], newest first (private bookmark list, never shown to others)
ACTIVITY = JsonFile("activity.json", [])        # [{"k": fav|download|printed|nozzle, "i": item id, "s": sha(sid), "t": unix}] for Trending decay
PRINTS = JsonFile("prints.json", [])            # "I printed this" photo records (photo files live in data/prints/)
