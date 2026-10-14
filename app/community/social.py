"""Favorites, timestamped activity (real Trending), remix credit chains and "I printed this" photos."""
from __future__ import annotations

import hashlib
import math
import secrets
import time

from ..config import DATA
from .store import ACTIVITY, FAVORITES, MODERATION, PRINTS

PDIR = DATA / "prints"
PDIR.mkdir(exist_ok=True)

# ---------------- activity + Trending ----------------
WEIGHTS = {"fav": 3.0, "printed": 5.0, "download": 1.0, "nozzle": 2.0}
HALF_LIFE_H = 72.0              # an action counts half as much after 3 days
WINDOW_S = 30 * 86400           # older actions are dropped (they would be < 0.1% weight anyway)
MAX_EVENTS = 200_000


def _who(sid: str) -> str:
    return hashlib.sha256(("act:" + (sid or "")).encode()).hexdigest()[:16]     # never the session id itself


def record(kind: str, item_id: str, sid: str, once: bool = True, now: float | None = None):
    """Log one action. `once`: one per (person, item, kind) inside the window, so tapping on/off cannot farm Trending."""
    now = now or time.time()
    who = _who(sid)

    def f(l):
        cutoff = now - WINDOW_S
        l[:] = [e for e in l if e["t"] >= cutoff][-MAX_EVENTS:]
        if once and any(e["k"] == kind and e["i"] == item_id and e["s"] == who for e in l):
            return
        l.append({"k": kind, "i": item_id, "s": who, "t": now})
    ACTIVITY.update(f)


def unrecord(kind: str, item_id: str, sid: str):
    who = _who(sid)
    ACTIVITY.update(lambda l: l.__setitem__(slice(None), [e for e in l if not (e["k"] == kind and e["i"] == item_id and e["s"] == who)]))


def heat(now: float | None = None) -> dict:
    """item id -> sum(weight * 0.5^(age_h / HALF_LIFE_H)) over recent favorites, downloads, 'I printed this' and nozzles."""
    now = now or time.time()
    out: dict = {}
    for e in ACTIVITY.read():
        age_h = max(0.0, (now - e["t"]) / 3600)
        if age_h * 3600 > WINDOW_S:
            continue
        out[e["i"]] = out.get(e["i"], 0.0) + WEIGHTS.get(e["k"], 0.0) * 0.5 ** (age_h / HALF_LIFE_H)
    return out


def trending_rank(h: float, legacy: float) -> float:
    """Recent activity dominates; the old all-time score (ln-damped totals x age decay) only breaks ties between quiet items."""
    return math.log1p(h) + 0.01 * legacy


# ---------------- favorites ----------------
def favorites(sid: str) -> list[str]:
    return list(FAVORITES.read().get(sid, []))


def is_fav(sid: str, item_id: str) -> bool:
    return item_id in FAVORITES.read().get(sid, [])


def set_fav(sid: str, item_id: str, on: bool) -> bool:
    def f(d):
        l = [x for x in d.get(sid, []) if x != item_id]
        if on:
            l.insert(0, item_id)
        if l:
            d[sid] = l[:500]
        else:
            d.pop(sid, None)
    FAVORITES.update(f)
    if on:
        record("fav", item_id, sid)
    else:
        unrecord("fav", item_id, sid)
    return on


def clear_person(sid: str):
    FAVORITES.update(lambda d: d.pop(sid, None))


# ---------------- "I printed this" photos ----------------
def add_print(item_id: str, sid: str, uid: str, username: str | None, data: bytes, ext: str, caption: str, ack,
             mod_result: str | None = None, *, nsfw: bool = False) -> dict:
    """Store a print photo. Always pending for a human — the image-moderation hook never auto-approves."""
    from . import imagemod
    verdict = mod_result or imagemod.review_upload(data, {"item_id": item_id, "uid": uid})
    if verdict == imagemod.REJECT:
        raise ValueError("That photo was refused. Please try a different one.")
    # Even if a future hook returns APPROVE, we still hold for a human (Zach: never auto-approve).
    pid = secrets.token_hex(6)
    (PDIR / f"{pid}.{ext}").write_bytes(data)
    rec = {"id": pid, "item_id": item_id, "owner_sid": sid, "uid": uid, "username": username, "ext": ext,
           "caption": caption, "created": time.time(), "photo_ack": ack, "status": "pending",
           "moderation": imagemod.NEEDS_HUMAN_REVIEW if verdict == imagemod.APPROVE else verdict,
           "nsfw": bool(nsfw)}
    PRINTS.update(lambda l: l.append(rec))      # held for moderator review (all ages); Trending counts it only once approved
    return rec


def status(p: dict) -> str:
    return p.get("status") or "pending"          # records from before review existed count as pending


def mark_existing_pending() -> int:
    """Startup migration: every photo without a status (made before review existed) becomes pending."""
    n = {"n": 0}

    def f(l):
        for p in l:
            if not p.get("status"):
                p["status"] = "pending"; n["n"] += 1
    if any(not p.get("status") for p in PRINTS.read()):
        PRINTS.update(f)
    return n["n"]


def pending() -> list[dict]:
    return sorted([p for p in PRINTS.read() if status(p) == "pending"], key=lambda p: p["created"])


def approve(pid: str) -> dict:
    out = {}

    def f(l):
        for p in l:
            if p["id"] == pid:
                p["status"] = "approved"; p["reviewed"] = time.time(); out.update(p)
    PRINTS.update(f)
    if not out:
        raise KeyError(pid)
    record("printed", out["item_id"], out["owner_sid"])
    return out


def reject(pid: str) -> bool:
    """Rejected photos are deleted: the record and the file."""
    p = get_print(pid)
    if not p:
        raise KeyError(pid)
    (PDIR / f"{pid}.{p['ext']}").unlink(missing_ok=True)
    PRINTS.update(lambda l: l.__setitem__(slice(None), [x for x in l if x["id"] != pid]))
    unrecord("printed", p["item_id"], p["owner_sid"])
    return True


def mod_key(pid: str) -> str:
    return "print:" + pid


def visible_to(p: dict, sid: str | None) -> bool:
    return status(p) == "approved" or (sid is not None and p["owner_sid"] == sid)


def prints_for(item_id: str, sid: str | None = None) -> list[dict]:
    """Approved photos, plus the viewer's own pending ones (shown to them as 'Waiting for review')."""
    hidden = set(MODERATION.read()["hidden"])
    return sorted([p for p in PRINTS.read() if p["item_id"] == item_id and mod_key(p["id"]) not in hidden and visible_to(p, sid)],
                  key=lambda p: -p["created"])


def get_print(pid: str) -> dict | None:
    return next((p for p in PRINTS.read() if p["id"] == pid), None)


def delete_print(pid: str, sid: str) -> bool:
    p = get_print(pid)
    if not p or p["owner_sid"] != sid:
        return False
    (PDIR / f"{pid}.{p['ext']}").unlink(missing_ok=True)
    PRINTS.update(lambda l: l.__setitem__(slice(None), [x for x in l if x["id"] != pid]))
    return True


def print_path(p: dict):
    f = PDIR / f"{p['id']}.{p['ext']}"
    return f if f.exists() else None
