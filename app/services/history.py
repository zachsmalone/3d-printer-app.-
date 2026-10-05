"""Build history (max N builds) stored on local disk: outputs/<id>/{meta.json,...}.

This is the seam for future social features: every build record already has an
`owner` and `visibility` field; swap this class for a DB/object-store backed
implementation (same method names) when accounts/feeds arrive.
"""
from __future__ import annotations

import json
import shutil
import threading
from datetime import datetime, timezone

from ..config import MAX_BUILDS, OUT


class HistoryFull(Exception):
    """Every build slot is taken AND every build is starred: nothing may be removed automatically."""


class BuildStore:
    def __init__(self, root=OUT, limit=MAX_BUILDS):
        self.root, self.limit = root, limit
        self.lock = threading.RLock()
        self.cache: dict = {}   # id -> geometry.Model (in-memory, rebuilt on demand)

    def dir(self, bid: str):
        if not bid.isalnum():
            raise KeyError(bid)
        return self.root / bid

    def list(self, owner: str | None = None) -> list[dict]:
        """All builds, or only those owned by session `owner` (the 5-build cap is per owner)."""
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
        p = self.dir(bid) / "meta.json"
        if not p.exists():
            raise KeyError(bid)
        return json.loads(p.read_text())

    def reserve(self, owner: str, auto_delete_oldest=False):
        """Call under `self.lock` before building. Raises HistoryFull when `owner` is at capacity."""
        items = self.list(owner)
        while len(items) >= self.limit:
            loose = [m for m in items if not m.get("favorite")]       # starred builds are never rolled off
            if not loose:
                raise HistoryFull()
            self.delete(loose[0]["id"])                                 # oldest un-starred build rolls off
            items = self.list(owner)

    def set_saved(self, bid: str):
        """Shared to the Showcase or sent to a class: kept longer than an ordinary build (see services/retention.py)."""
        with self.lock:
            try:
                meta = self.get(bid)
            except KeyError:
                return
            if not meta.get("saved"):
                meta["saved"] = True
                self.save(meta)

    def set_favorite(self, bid: str, fav: bool) -> dict:
        with self.lock:
            meta = self.get(bid)
            meta["favorite"] = bool(fav)
            self.save(meta)
            return meta

    def save(self, meta: dict):
        meta.setdefault("created", datetime.now(timezone.utc).isoformat())
        meta.setdefault("owner", "local")        # legacy field
        meta.setdefault("visibility", "private")  # private | followers | public (see community/privacy.py)
        (self.dir(meta["id"]) / "meta.json").write_text(json.dumps(meta, indent=1, default=str))

    def claim_unowned(self, sid: str):
        """Builds made before ownership existed belong to the first session that lists builds (single-user era)."""
        with self.lock:
            for m in self.list():
                if not m.get("owner_sid"):
                    m["owner_sid"] = sid
                    m["visibility"] = "private"
                    self.save(m)

    def delete(self, bid: str):
        with self.lock:
            shutil.rmtree(self.dir(bid), ignore_errors=True)
            self.cache.pop(bid, None)
            from . import editproj
            editproj._BASES.pop(bid, None)
            editproj._STATES.pop(bid, None)


store = BuildStore()
