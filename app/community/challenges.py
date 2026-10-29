"""Prize-free monthly Showcase challenges.

One themed challenge is open at a time. Entries are the maker's own Showcase posts.
No cash and no prizes: 1st, 2nd and 3rd earn winner badges only.

Tiebreak: more likes rank higher. If the like counts match, the earlier entry places higher.
Winners are frozen the first time they are read on or after winners_at, using likes at that moment.
"""
from __future__ import annotations

import secrets
import time
from datetime import datetime, timezone

from .store import CHALLENGE_ENTRIES, CHALLENGES

# Older Remix challenge. Kept so old links resolve, and closed so it is not the live theme.
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
        "Tip links stay optional. ZEIM never nags, and never takes a cut of tips or of sales a maker makes from their own link. Showcase downloads stay free.",
        "18+ only. Keep it within the Community Guidelines.",
    ],
    "prize_free": True,
    "status": "closed",
    "created": 0,
}

# Current month's theme. Open through 24 Dec 2026. Winners appear on 25 Dec.
# Next month is named only. A later month is not previewed.
XMAS_ID = "ch_2026_12"
XMAS = {
    "id": XMAS_ID,
    "slug": "christmas",
    "title": "Christmas",
    "theme": "christmas",
    "blurb": "December's prompt is Christmas. A star, a bauble, a tiny sleigh, or a joke only your tree would get. "
             "Enter with one Showcase post you already published. "
             "1st, 2nd and 3rd earn a monthly winner badge. Likes on entries earn badges too. "
             "No cash and no prizes.",
    "next_theme": "January: a quiet fresh start. One small useful thing for a desk or a pocket.",
    "opens": "2026-10-01T00:00:00+00:00",
    "closes": "2026-12-24T23:59:59+00:00",
    "winners_at": "2026-12-25T00:00:00+00:00",
    "rules": [
        "Enter with one of your own Showcase posts.",
        "1st, 2nd and 3rd earn a monthly winner badge. Likes on entries earn badges too.",
        "No cash and no prizes. Badges only.",
        "If two entries have the same number of likes, the one entered earlier places higher.",
        "Tip links stay optional. ZEIM never nags, and never takes a cut of tips or of sales a maker makes from their own link. Showcase downloads stay free.",
        "18+ only. Keep it within the Community Guidelines.",
    ],
    "prize_free": True,
    "status": "open",
    "created": 0,
}


class Bad(ValueError):
    pass


_OLD_TIP_RULE = "Tip links stay optional; ZEIM never nags and takes no cut of tips."


def current_time() -> datetime:
    """Clock for open, close, and winner reveal. Tests may set current_time.override."""
    override = getattr(current_time, "override", None)
    if isinstance(override, datetime):
        return override if override.tzinfo else override.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def _parse(value) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def phase(c: dict, now: datetime | None = None) -> str:
    """open, upcoming, or closed. Winner reveal is still closed; winners_visible tells them apart."""
    now = now or current_time()
    if c.get("status") == "closed" and not c.get("closes"):
        return "closed"
    opens, closes = _parse(c.get("opens")), _parse(c.get("closes"))
    winners_at = _parse(c.get("winners_at"))
    if winners_at and now >= winners_at:
        return "closed"
    if closes and now > closes:
        return "closed"
    if opens and now < opens:
        return "upcoming"
    return "open"


def winners_visible(c: dict, now: datetime | None = None) -> bool:
    now = now or current_time()
    winners_at = _parse(c.get("winners_at"))
    return bool(winners_at and now >= winners_at)


def _likes(item_id: str) -> int:
    from .store import ENGAGEMENT
    rows = ENGAGEMENT.read().get("likes", {}).get(item_id, [])
    return len(rows) if isinstance(rows, list) else 0


def rank_entries(cid: str) -> list[dict]:
    """More likes first. Equal likes: the earlier entry wins. Id is a last resort so the order never flips."""
    rows = entries(cid)
    return sorted(rows, key=lambda e: (-_likes(e["item_id"]), float(e.get("created") or 0), e.get("id") or ""))


def ensure_winners(c: dict, now: datetime | None = None) -> list[dict]:
    """Freeze the top 3 once, on or after winners_at. Later likes do not move them."""
    now = now or current_time()
    if not winners_visible(c, now):
        return []
    if c.get("winners_frozen"):
        return list(c.get("winners") or [])
    ranked = rank_entries(c["id"])[:3]
    winners = [{
        "place": i,
        "item_id": e["item_id"],
        "uid": e.get("uid") or "",
        "owner_sid": e.get("owner_sid") or "",
        "likes": _likes(e["item_id"]),
        "entered": e.get("created") or 0,
    } for i, e in enumerate(ranked, start=1)]

    def f(rows):
        for row in rows:
            if row.get("id") == c["id"] and not row.get("winners_frozen"):
                row["winners"] = winners
                row["winners_frozen"] = True
                row["status"] = "closed"
    CHALLENGES.update(f)
    c["winners"] = winners
    c["winners_frozen"] = True
    return winners


def _ensure_seed():
    """Christmas is the open theme. The old Remix challenge, if stored, stays closed."""
    def f(rows):
        hit = next((c for c in rows if c.get("id") == XMAS_ID), None)
        if hit is None:
            seed = dict(XMAS)
            seed["created"] = time.time()
            seed["winners"] = []
            seed["winners_frozen"] = False
            rows.insert(0, seed)
        else:
            for key in ("title", "slug", "theme", "blurb", "next_theme", "opens", "closes", "winners_at", "rules"):
                hit[key] = XMAS[key]
            hit["prize_free"] = True
        for c in rows:
            if c.get("id") == REMIX_ID:
                c["status"] = "closed"
                if _OLD_TIP_RULE in (c.get("rules") or []):
                    c["rules"] = [REMIX["rules"][2] if r == _OLD_TIP_RULE else r for r in c["rules"]]
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


def pull_item(item_id: str) -> None:
    """Drop every challenge entry that used this Showcase project."""
    if not item_id:
        return

    def f(l):
        l[:] = [e for e in l if e.get("item_id") != item_id]
    CHALLENGE_ENTRIES.update(f)


def entry_for(cid: str, sid: str) -> dict | None:
    """This person's entry on a challenge, if they have one. One remix per person."""
    if not sid:
        return None
    c = get(cid)
    if not c:
        return None
    return next((e for e in entries(c["id"]) if e.get("owner_sid") == sid), None)


def enter(cid: str, *, item_id: str, sid: str, uid: str, remix_of: str = "",
          now: float | None = None) -> dict:
    """Record an entry. The caller has checked that the Showcase post belongs to this person.

    The old Remix theme still requires a remix credit. A monthly theme takes any of their posts.
    """
    c = get(cid)
    if not c:
        raise KeyError(cid)
    if phase(c) != "open":
        raise Bad("This challenge is closed.")
    if c.get("theme") == "remix" and not remix_of:
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


def public(c: dict, *, entry_count: int | None = None, now: datetime | None = None) -> dict:
    now = now or current_time()
    n = entry_count if entry_count is not None else len(entries(c["id"]))
    show = winners_visible(c, now)
    winners = ensure_winners(c, now) if show else []
    return {"id": c["id"], "slug": c.get("slug") or c["id"], "title": c["title"],
            "theme": c.get("theme") or "", "blurb": c.get("blurb") or "",
            "next_theme": c.get("next_theme") or "",
            "rules": list(c.get("rules") or []),
            "prize_free": True,          # always; never advertise prizes
            "status": phase(c, now),
            "opens": c.get("opens") or "",
            "closes": c.get("closes") or "",
            "winners_at": c.get("winners_at") or "",
            "winners_visible": show,
            "winners": winners,
            "entry_count": n,
            "created": c.get("created") or 0}
