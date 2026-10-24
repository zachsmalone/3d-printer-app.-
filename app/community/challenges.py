"""Prize-free themed Showcase challenges.

Humble by design: no cash, no prizes, no ranking rewards, no tip nags.
The first challenge is Remix — enter by publishing a credited remix.
"""
from __future__ import annotations

import secrets
import time

from .store import CHALLENGE_ENTRIES, CHALLENGES

# Built-in starter. Id is stable so bookmarks and tests stay put.
REMIX_ID = "ch_remix"
REMIX = {
    "id": REMIX_ID,
    "slug": "remix",
    "title": "Remix challenge",
    "theme": "remix",
    "blurb": "Take a public remixable project, make your own version, and share the credited remix. "
             "Prize-free: no cash, no prizes, no ranking rewards — just makers helping makers.",
    "rules": [
        "Your entry must be a credited remix of a public Showcase project.",
        "Prize-free: ZEIM offers no cash or prizes for this challenge.",
        "Tip links stay optional; ZEIM never nags and takes no cut of tips.",
        "18+ only. Keep it within the Community Guidelines.",
    ],
    "prize_free": True,
    "status": "open",
    "created": 0,
}


class Bad(ValueError):
    pass


def _ensure_seed():
    """Idempotent: the Remix challenge always exists."""
    if any(c.get("id") == REMIX_ID for c in CHALLENGES.read()):
        return

    def f(l):
        if not any(c.get("id") == REMIX_ID for c in l):
            seed = dict(REMIX)
            seed["created"] = time.time()
            l.insert(0, seed)
    CHALLENGES.update(f)


def list_all() -> list[dict]:
    _ensure_seed()
    return sorted(CHALLENGES.read(), key=lambda c: c.get("created") or 0, reverse=True)


def get(cid: str) -> dict | None:
    _ensure_seed()
    return next((c for c in CHALLENGES.read() if c["id"] == cid or c.get("slug") == cid), None)


def entries(cid: str) -> list[dict]:
    return sorted([e for e in CHALLENGE_ENTRIES.read() if e["challenge_id"] == cid],
                  key=lambda e: e["created"], reverse=True)


def entered(cid: str, item_id: str) -> bool:
    return any(e["challenge_id"] == cid and e["item_id"] == item_id for e in CHALLENGE_ENTRIES.read())


def enter(cid: str, *, item_id: str, sid: str, uid: str, remix_of: str,
          now: float | None = None) -> dict:
    """Record an entry. Caller must have verified the item is a public remix by this user."""
    c = get(cid)
    if not c:
        raise KeyError(cid)
    if c.get("status") != "open":
        raise Bad("This challenge is closed.")
    if not remix_of:
        raise Bad("This challenge is for credited remixes. Publish with a Remixed-from link first.")
    if entered(cid, item_id):
        raise Bad("That project is already entered.")
    now = now or time.time()
    rec = {"id": "ce_" + secrets.token_hex(5), "challenge_id": c["id"], "item_id": item_id,
           "owner_sid": sid, "uid": uid, "remix_of": remix_of, "created": now}

    def f(l):
        if any(e["challenge_id"] == c["id"] and e["item_id"] == item_id for e in l):
            raise Bad("That project is already entered.")
        # one active entry per person per challenge keeps farming down
        if any(e["challenge_id"] == c["id"] and e["owner_sid"] == sid for e in l):
            raise Bad("You already entered this challenge. One remix per person.")
        l.append(rec)
    CHALLENGE_ENTRIES.update(f)
    return rec


def public(c: dict, *, entry_count: int | None = None) -> dict:
    n = entry_count if entry_count is not None else len(entries(c["id"]))
    return {"id": c["id"], "slug": c.get("slug") or c["id"], "title": c["title"],
            "theme": c.get("theme") or "", "blurb": c.get("blurb") or "",
            "rules": list(c.get("rules") or []),
            "prize_free": True,          # always; never advertise prizes
            "status": c.get("status") or "open",
            "entry_count": n,
            "created": c.get("created") or 0}
