"""Build history (max N builds per owner): outputs/<id>/{model files, thumb...}.

Two storage modes for the METADATA (the model files always live on disk in
outputs/<id>/; object storage is a separate concern):
  * json (default): meta.json inside each build folder, as before.
  * db (ZEIM_STORAGE=db): metadata rows in SQLite (app/db.py) — indexed by owner
    and visibility, one source of truth, atomic transactions, multi-worker safe.
    The meta.json file is NOT written in db mode; every reader goes through
    BuildStore so both modes behave identically.

This is the seam for social features: every build record already has an `owner`
and `visibility` field; the same method names work against either backend.
"""
from __future__ import annotations

import json
import shutil
import threading
from datetime import datetime, timezone

from .. import config
from ..config import MAX_BUILDS, OUT


class HistoryFull(Exception):
    """Every build slot is taken AND every build is starred: nothing may be removed automatically."""


class BuildStore:
    def __init__(self, root=OUT, limit=MAX_BUILDS):
        self.root, self.limit = root, limit
        self.lock = threading.RLock()
        self.cache: dict = {}   # id -> geometry.Model (in-memory, rebuilt on demand)

    def _db(self):
        # db mode is read from the live config so tests can flip it per test
        if config.STORAGE_MODE != "db":
            return None
        from .. import db
        return db

    def dir(self, bid: str):
        if not bid.isalnum():
            raise KeyError(bid)
        return self.root / bid

    def list(self, owner: str | None = None) -> list[dict]:
        """All builds, or only those owned by session `owner` (the 5-build cap is per owner)."""
        db = self._db()
        if db is not None:
            return db.build_list(owner)
        out = []
        for p in self.root.glob("*/meta.json"):
            try:
                out.append(json.loads(p.read_text()))
            except Exception:
                pass
        if owner is not None:
            out = [m for m in out if m.get("owner_sid") == owner]
        return sorted(out, key=lambda m: m["created"])

    def get(self, bid: str) -> dict:
        db = self._db()
        if db is not None:
            meta = db.build_get(bid)
            if meta is None:
                raise KeyError(bid)
            return meta
        p = self.dir(bid) / "meta.json"
        if not p.exists():
            raise KeyError(bid)
        return json.loads(p.read_text())

    def reserve(self, owner: str, auto_delete_oldest=False):
        """Call under `self.lock` before building. Raises HistoryFull when `owner` is at capacity.
        Roll-off semantics are identical in both storage modes: the oldest UN-STARRED build is
        removed to make room; starred builds are never rolled off."""
        db = self._db()
        if db is not None:
            items = db.build_list(owner)
            while len(items) >= self.limit:
                loose = [m for m in items if not m.get("favorite")]
                if not loose:
                    raise HistoryFull()
                oldest = loose[0]
                db.build_delete(oldest["id"])
                self._purge_cached(oldest["id"])
                items = [m for m in items if m["id"] != oldest["id"]]
            return
        items = self.list(owner)
        while len(items) >= self.limit:
            loose = [m for m in items if not m.get("favorite")]       # starred builds are never rolled off
            if not loose:
                raise HistoryFull()
            self.delete(loose[0]["id"])                                 # oldest un-starred build rolls off
            items = self.list(owner)

    def set_saved(self, bid: str):
        """Shared to the Showcase or sent to a class: kept longer than an ordinary build (see services/retention.py)."""
        db = self._db()
        if db is not None:
            def _mark(meta):
                meta["saved"] = True
            try:
                db.build_update(bid, _mark)
            except KeyError:
                return
            return
        with self.lock:
            try:
                meta = self.get(bid)
            except KeyError:
                return
            if not meta.get("saved"):
                meta["saved"] = True
                self.save(meta)

    def set_favorite(self, bid: str, fav: bool) -> dict:
        db = self._db()
        if db is not None:
            def _mark(meta):
                meta["favorite"] = bool(fav)
            return db.build_update(bid, _mark)
        with self.lock:
            meta = self.get(bid)
            meta["favorite"] = bool(fav)
            self.save(meta)
            return meta

    def save(self, meta: dict):
        meta.setdefault("created", datetime.now(timezone.utc).isoformat())
        meta.setdefault("owner", "local")        # legacy field
        meta.setdefault("visibility", "private")  # private | followers | public (see community/privacy.py)
        db = self._db()
        if db is not None:
            db.build_save(meta)
            return
        (self.dir(meta["id"]) / "meta.json").write_text(json.dumps(meta, indent=1, default=str))

    def claim_unowned(self, sid: str):
        """Builds made before ownership existed belong to the first session that lists builds (single-user era)."""
        db = self._db()
        if db is not None:
            db.build_claim_unowned(sid)
            return
        with self.lock:
            for m in self.list():
                if not m.get("owner_sid"):
                    m["owner_sid"] = sid
                    m["visibility"] = "private"
                    self.save(m)

    def _purge_cached(self, bid: str):
        self.cache.pop(bid, None)
        from . import editproj
        editproj._BASES.pop(bid, None)
        editproj._STATES.pop(bid, None)

    def delete(self, bid: str):
        with self.lock:
            db = self._db()
            if db is not None:
                db.build_delete(bid)
            shutil.rmtree(self.dir(bid), ignore_errors=True)
            self._purge_cached(bid)


store = BuildStore()
