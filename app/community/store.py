"""Tiny locked JSON file store (stand-in for a database).

A storage-mode switch lets the app fall back to JSON while a DB-backed
implementation is introduced. The JSON files are backed up before any migration
and remain read-only as a rollback fallback.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
from pathlib import Path

from ..config import DATA, STORAGE_MODE

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
        self.path: Path = DATA / name
        self.default = default

    def _warn_if_db_mode(self):
        if STORAGE_MODE == "db":
            import logging
            logging.getLogger("zeim.storage").warning(
                "ZEIM_STORAGE=db is active; JSON fallback is read-only and backups remain in %s",
                (DATA / "backups").as_posix(),
            )

    def read(self):
        with _lock:
            self._warn_if_db_mode()
            if self.path.exists():
                try:
                    return json.loads(self.path.read_text())
                except Exception:
                    pass
            return json.loads(json.dumps(self.default))

    def write(self, data):
        """Atomic (temp file + rename) and private: only the account that runs the server can read these files (mode 600)."""
        with _lock:
            self._warn_if_db_mode()
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
