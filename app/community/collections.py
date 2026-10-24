"""Showcase collections: creators group their own models into named lists.

Original ZEIM code. Public adults can browse a creator's collections and open one
to see its models. No featured/boosted lists, no ranking — just named groups.
Behaviour ideas (named public lists on a maker's page) come from watching Printables
and Thingiverse publicly; no code from those sites is used. See docs/specs/showcase-gaps.md.
"""
from __future__ import annotations

import secrets
import time

from .store import COLLECTIONS

MAX_COLLECTIONS = 50       # per person
MAX_ITEMS = 300            # per collection
NAME_MAX = 60


class Bad(ValueError):
    pass


def of_owner(sid: str) -> list[dict]:
    """Every collection this session owns, newest first."""
    return sorted([c for c in COLLECTIONS.read() if c["owner_sid"] == sid],
                  key=lambda c: c.get("updated") or c.get("created") or 0, reverse=True)


def public_of(uid: str) -> list[dict]:
    """Public collections for a creator id (uid), newest first. Empty ones stay listed so a
    fresh collection still appears on the profile while the maker fills it."""
    return sorted([c for c in COLLECTIONS.read() if c.get("uid") == uid and c.get("public")],
                  key=lambda c: c.get("updated") or c.get("created") or 0, reverse=True)


def get(cid: str) -> dict | None:
    return next((c for c in COLLECTIONS.read() if c["id"] == cid), None)


def holding(sid: str, item_id: str) -> list[str]:
    return [c["id"] for c in of_owner(sid) if item_id in c.get("items", [])]


def create(sid: str, uid: str, name: str, *, public: bool = True, now: float | None = None) -> dict:
    name = (name or "").strip()
    if not name:
        raise Bad("Give the collection a name.")
    if len(name) > NAME_MAX:
        raise Bad(f"Name is too long (max {NAME_MAX} characters).")
    now = now or time.time()
    rec = {"id": "col_" + secrets.token_hex(6), "owner_sid": sid, "uid": uid, "name": name,
           "public": bool(public), "items": [], "created": now, "updated": now}

    def f(l):
        if sum(1 for c in l if c["owner_sid"] == sid) >= MAX_COLLECTIONS:
            raise Bad(f"You can have up to {MAX_COLLECTIONS} collections.")
        if any(c["owner_sid"] == sid and c["name"].lower() == name.lower() for c in l):
            raise Bad("You already have a collection with that name.")
        l.append(rec)
    COLLECTIONS.update(f)
    return rec


def rename(sid: str, cid: str, name: str) -> dict:
    name = (name or "").strip()
    if not name:
        raise Bad("Give the collection a name.")
    if len(name) > NAME_MAX:
        raise Bad(f"Name is too long (max {NAME_MAX} characters).")
    out: dict = {}

    def f(l):
        c = next((c for c in l if c["id"] == cid and c["owner_sid"] == sid), None)
        if not c:
            raise KeyError(cid)
        if any(x["owner_sid"] == sid and x["id"] != cid and x["name"].lower() == name.lower() for x in l):
            raise Bad("You already have a collection with that name.")
        c["name"] = name
        c["updated"] = time.time()
        out.update(c)
    COLLECTIONS.update(f)
    return out


def set_public(sid: str, cid: str, public: bool) -> dict:
    out: dict = {}

    def f(l):
        c = next((c for c in l if c["id"] == cid and c["owner_sid"] == sid), None)
        if not c:
            raise KeyError(cid)
        c["public"] = bool(public)
        c["updated"] = time.time()
        out.update(c)
    COLLECTIONS.update(f)
    return out


def delete(sid: str, cid: str) -> bool:
    def f(l):
        n = len(l)
        l[:] = [c for c in l if not (c["id"] == cid and c["owner_sid"] == sid)]
        return len(l) != n
    return bool(COLLECTIONS.update(f))


def set_item(sid: str, cid: str, item_id: str, on: bool) -> dict:
    """Add or remove one of the owner's own model ids. Caller must have verified ownership."""
    out: dict = {}

    def f(l):
        c = next((c for c in l if c["id"] == cid and c["owner_sid"] == sid), None)
        if not c:
            raise KeyError(cid)
        items = [x for x in c.get("items", []) if x != item_id]
        if on:
            if len(items) >= MAX_ITEMS:
                raise Bad(f"A collection holds up to {MAX_ITEMS} projects.")
            items.insert(0, item_id)
        c["items"], c["updated"] = items, time.time()
        out.update(c)
    COLLECTIONS.update(f)
    return out
