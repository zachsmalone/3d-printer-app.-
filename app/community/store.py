"""Community data stores.

Two storage modes (ZEIM_STORAGE): "json" (default) keeps the locked JSON files; "db" backs the
SAME interface with SQLite (app/db.py) — one source of truth, atomic transactions, multi-worker
safe. The JSON files are backed up before any migration and remain as a rollback fallback.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
from pathlib import Path

from .. import config
from ..config import DATA

_lock = threading.RLock()


def _backup_dir() -> Path:
    ts = time.strftime("%Y%m%d-%H%M%S")
    path = DATA / "backups" / f"json-backup-{ts}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def backup_json_data() -> Path:
    """Copy every JSON file to a timestamped backup directory."""
    if not DATA.exists():
        return _backup_dir()
    backup = _backup_dir()
    for p in sorted(DATA.glob("*.json")):
        shutil.copy2(p, backup / p.name)
    return backup


def freeze_json_fallback() -> list[Path]:
    """Make the JSON files read-only to preserve them as a rollback source."""
    changed = []
    for p in sorted(DATA.glob("*.json")):
        try:
            if (p.stat().st_mode & 0o222) != 0:
                os.chmod(p, p.stat().st_mode & ~0o222)
                changed.append(p)
        except OSError:
            pass
    return changed


class JsonFile:
    def __init__(self, name: str, default):
        self.name: str = name[:-5] if name.endswith(".json") else name   # doc key + file stem
        self.path: Path = DATA / (self.name + ".json")
        self.default = default

    def _db(self):
        # db mode is read from the live config so tests can flip it per test
        if config.STORAGE_MODE != "db":
            return None
        from .. import db
        return db

    def read(self):
        db = self._db()
        if db is not None:
            return db.doc_read(self.name, self.default)
        with _lock:
            if self.path.exists():
                try:
                    return json.loads(self.path.read_text())
                except Exception:
                    pass
            return json.loads(json.dumps(self.default))

    def write(self, data):
        """Atomic and private: only the account that runs the server can read these files (mode 600).
        In db mode the database is the one source of truth — a failure raises, never falls back to JSON."""
        db = self._db()
        if db is not None:
            db.doc_write(self.name, data)
            return
        with _lock:
            tmp = self.path.with_name(self.path.name + ".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as fh:
                fh.write(json.dumps(data, indent=1, default=str))
            os.replace(tmp, self.path)

    def update(self, fn):
        db = self._db()
        if db is not None:
            return db.doc_update(self.name, self.default, fn)
        with _lock:
            d = self.read()
            r = fn(d)
            self.write(d)
            return r


USERS = JsonFile("users", {})          # sid -> account (DOB, flags)
PREFS = JsonFile("prefs", {})          # sid -> personalization data
LISTINGS = JsonFile("projects", [])    # user-published (free) projects
MODERATION = JsonFile("moderation", {"hidden": [], "reports": []})
# 2026-10-12: school features removed. A pre-existing data/classrooms.json (and data/classroom_projects/) is no longer
# read or written by any code; it is left on disk untouched (no deletion of existing data). Owner decides on cleanup.
PROGRESS = JsonFile("education_progress", {})
ENGAGEMENT = JsonFile("engagement", {"likes": {}, "downloads": {}})   # item id -> [visitor sids] (one each)
AGE_BLOCKS = JsonFile("age_blocks", {})   # sha256(sid)[:24] -> unix time the lock ends (no DOB, no age is ever stored here)
# Community features (Oct 2026): favorites, timestamped activity for Trending, "I printed this" photos
FAVORITES = JsonFile("favorites", {})      # sid -> [item ids], newest first (private bookmark list, never shown to others)
ACTIVITY = JsonFile("activity", [])        # [{"k": fav|download|printed|nozzle, "i": item id, "s": sha(sid), "t": unix}] for Trending decay
PRINTS = JsonFile("prints", [])            # "I printed this" photo records (photo files live in data/prints/)
# Showcase collections: creator-named groups of their own models (docs/specs/showcase-gaps.md #2)
COLLECTIONS = JsonFile("collections", [])   # [{id, owner_sid, uid, name, public, items: [iid], created, updated}]
