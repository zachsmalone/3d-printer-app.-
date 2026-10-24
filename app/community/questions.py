"""Creator-answered project questions on Showcase listings.

Public Q&A on the project page — not DMs, not private threads. Asker posts a
question (word-filtered); only the project's creator can answer. Visitors see
answered questions; the creator also sees unanswered ones waiting for a reply.
"""
from __future__ import annotations

import secrets
import time

from .store import QUESTIONS

TEXT_MAX = 280
ANSWER_MAX = 1000
MAX_OPEN_PER_ASKER = 5          # unanswered questions one person may have on one project
MAX_PER_PROJECT = 200


class Bad(ValueError):
    pass


def for_item(item_id: str) -> list[dict]:
    return sorted([q for q in QUESTIONS.read() if q["item_id"] == item_id],
                  key=lambda q: q["created"], reverse=True)


def get(qid: str) -> dict | None:
    return next((q for q in QUESTIONS.read() if q["id"] == qid), None)


def ask(item_id: str, *, sid: str, uid: str, username: str | None, text: str,
        now: float | None = None) -> dict:
    text = (text or "").strip()
    if not text:
        raise Bad("Write a question first.")
    if len(text) > TEXT_MAX:
        raise Bad(f"Questions can be at most {TEXT_MAX} characters.")
    now = now or time.time()
    rec = {"id": "q_" + secrets.token_hex(6), "item_id": item_id, "asker_sid": sid,
           "asker_uid": uid, "asker_username": username or "", "text": text,
           "created": now, "answer": "", "answered_at": None, "status": "open"}

    def f(l):
        mine_open = sum(1 for q in l if q["item_id"] == item_id and q["asker_sid"] == sid
                        and q.get("status") == "open" and not q.get("answer"))
        if mine_open >= MAX_OPEN_PER_ASKER:
            raise Bad(f"You already have {MAX_OPEN_PER_ASKER} unanswered questions on this project.")
        if sum(1 for q in l if q["item_id"] == item_id) >= MAX_PER_PROJECT:
            raise Bad("This project has enough questions for now.")
        l.append(rec)
    QUESTIONS.update(f)
    return rec


def answer(qid: str, *, owner_sid: str, text: str, now: float | None = None) -> dict:
    text = (text or "").strip()
    if not text:
        raise Bad("Write an answer first.")
    if len(text) > ANSWER_MAX:
        raise Bad(f"Answers can be at most {ANSWER_MAX} characters.")
    now = now or time.time()
    out: dict = {}

    def f(l):
        q = next((q for q in l if q["id"] == qid), None)
        if not q:
            raise KeyError(qid)
        # ownership of the project is checked by the API; here we only mutate
        q["answer"] = text
        q["answered_at"] = now
        q["status"] = "answered"
        q["answered_by_sid"] = owner_sid
        out.update(q)
    QUESTIONS.update(f)
    return out


def remove(qid: str, *, sid: str, is_owner: bool) -> bool:
    """Asker may delete their own unanswered question; project owner may delete any."""
    q = get(qid)
    if not q:
        return False
    if not is_owner and (q["asker_sid"] != sid or q.get("answer")):
        return False

    def f(l):
        l[:] = [x for x in l if x["id"] != qid]
    QUESTIONS.update(f)
    return True


def visible(q: dict, *, actor_sid: str | None, owner_sid: str | None) -> bool:
    """Answered questions are public. Open ones: asker + project owner only."""
    if q.get("answer"):
        return True
    return bool(actor_sid and (actor_sid == q.get("asker_sid") or actor_sid == owner_sid))


def public(q: dict, *, mine: bool = False, can_answer: bool = False) -> dict:
    return {"id": q["id"], "text": q.get("text") or "", "created": q["created"],
            "by": ("@" + q["asker_username"]) if q.get("asker_username") else "a ZEIM maker",
            "answer": q.get("answer") or "", "answered_at": q.get("answered_at"),
            "status": "answered" if q.get("answer") else "open",
            "mine": mine, "can_answer": can_answer and not q.get("answer")}
