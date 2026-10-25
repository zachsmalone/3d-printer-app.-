"""In-app ZeimFeedback. The destination address lives only in this module.

The page never shows it, and the JSON response never echoes it. Visitors do not
send from their own mailbox: the server posts the note, or stores it when mail
is off and says so.
"""
from __future__ import annotations

import json
import os
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from app import config
from app.api.textcap import ip as client_ip
from app.api.textcap import text_in
from app.auth.mailer import mailer_from_env
from app.community.identity import Actor, get_actor
from app.core import ratelimit

router = APIRouter(prefix="/api", tags=["feedback"])

# Product destination. Do not copy this into static HTML, JS, CSS, or API responses.
DESTINATION = "zeimfeedback@mail.grokbot.com"

SAVED_MESSAGE = "Saved on this server. It has not been emailed yet."
SENT_MESSAGE = "Sent. Thank you."


def _who(actor: Actor) -> str:
    user = actor.user or {}
    name = str(user.get("username") or user.get("display_name") or "").strip()
    return (name or "guest")[:80]


@router.post("/feedback")
def post_feedback(body: dict, request: Request, actor: Actor = Depends(get_actor)):
    try:
        text = text_in(body.get("message") if body.get("message") is not None else body.get("text"), 4000, "Message")
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not text:
        raise HTTPException(400, "Write a message first.")
    who = _who(actor)
    key = "feedback:" + (actor.sid or client_ip(request))
    if not ratelimit.hit(key, 8, 3600):
        raise HTTPException(429, "That's a lot of feedback for one hour. Please wait a while.")
    note = f"From: {who}\n\n{text}\n"
    emailed = False
    try:
        mailer_from_env(os.environ).send(DESTINATION, "ZEIM feedback", note)
        emailed = True
    except Exception:
        folder = config.DATA / "feedback"
        folder.mkdir(parents=True, exist_ok=True)
        rec = {"at": time.time(), "who": who, "text": text, "emailed": False}
        (folder / f"{uuid.uuid4().hex}.json").write_text(json.dumps(rec), encoding="utf-8")
    return {
        "ok": True,
        "emailed": emailed,
        "message": SENT_MESSAGE if emailed else SAVED_MESSAGE,
    }
