"""RET8: private numbers for a Showcase publisher about their OWN posts (downloads, favorites, tip-link clicks).
Tip clicks are counted once per visitor; only a short one-way hash of the visitor session is kept, never who."""
from __future__ import annotations

import hashlib

from . import catalog
from .store import FAVORITES, JsonFile

TIPCLICKS = JsonFile("tipclicks", {})      # item id -> [short sha256 of visitor sid]


def _h(sid: str) -> str:
    return hashlib.sha256(("tip\0" + sid).encode()).hexdigest()[:16]


def record_tip_click(item_id: str, sid: str) -> bool:
    item = next((i for i in catalog._all() if i["id"] == item_id and not i["hidden"]), None)
    if not item or not item.get("tip_url") or item.get("owner_sid") == sid:
        return False                       # no link, or the owner clicking their own link
    h = _h(sid); added = []
    def fn(d):
        lst = d.setdefault(item_id, [])
        if h not in lst: lst.append(h); added.append(1)
        return d
    TIPCLICKS.update(fn)
    return bool(added)


def for_owner(actor) -> list[dict]:
    favs = FAVORITES.read(); clicks = TIPCLICKS.read()
    fav_count: dict[str, int] = {}
    for sid, ids in favs.items():
        for i in set(ids or []):
            fav_count[i] = fav_count.get(i, 0) + 1
    return [{"id": i["id"], "title": i["title"], "downloads": len(i.get("_dlers", [])), "likes": len(i.get("_likers", [])),
             "favorites": fav_count.get(i["id"], 0), "tip_clicks": len(clicks.get(i["id"], [])), "has_tip": bool(i.get("tip_url"))}
            for i in catalog.mine(actor)]
