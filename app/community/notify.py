"""Small in-app notices. No email is stored or sent from here."""
from __future__ import annotations

import secrets
import time

from .store import JsonFile

NOTICES = JsonFile("notices", [])
CAP = 40


def add(sid: str, kind: str, text: str, *, item_id: str = "", user_id: str = "") -> dict:
    if not sid or not text:
        return {}
    rec = {"id": "nt_" + secrets.token_hex(4), "sid": sid, "kind": kind, "text": text[:180],
           "item_id": item_id, "user_id": user_id, "created": time.time(), "read": False}

    def f(rows):
        rows.append(rec)
        mine = [n for n in rows if n.get("sid") == sid]
        if len(mine) > CAP:
            drop = {n["id"] for n in mine[:-CAP]}
            rows[:] = [n for n in rows if n.get("id") not in drop]
    NOTICES.update(f)
    return rec


def for_user(sid: str) -> list[dict]:
    rows = [n for n in NOTICES.read() if n.get("sid") == sid]
    return sorted(rows, key=lambda n: n.get("created") or 0, reverse=True)[:CAP]


def unread(sid: str) -> int:
    return sum(1 for n in NOTICES.read() if n.get("sid") == sid and not n.get("read"))


def mark_read(sid: str, notice_id: str = "") -> None:
    def f(rows):
        for n in rows:
            if n.get("sid") != sid:
                continue
            if notice_id and n.get("id") != notice_id:
                continue
            n["read"] = True
    NOTICES.update(f)
