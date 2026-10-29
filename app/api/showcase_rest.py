"""Showcase rest (task 4): print settings, project Q&A, prize-free challenges.

No DMs. No cash/prizes. Tip links stay optional elsewhere; ZEIM takes no tip cut.
"""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from .. import config
from ..core import ratelimit
from ..community import badges, catalog, challenges, questions, safety
from ..community.identity import Actor, get_actor
from .community import D
from .textcap import text_in

router = APIRouter(prefix="/api", tags=["showcase-rest"])


def _ip(request: Request) -> str:
    return (request.client.host if request.client else "") or "unknown"


# ---------------- print settings on models ----------------
@router.put("/showcase/{iid}/print-settings")
def put_print_settings(iid: str, body: dict, actor: Actor = Depends(get_actor)):
    """Owner only: optional printer/material/layer/infill/supports/notes. Empty body clears."""
    try:
        return catalog.public(catalog.set_print_settings(actor, iid, body.get("print_settings", body)), actor)
    except catalog.Denied as e:
        raise D(e)


# ---------------- creator-answered project questions (no DMs) ----------------
@router.get("/showcase/{iid}/questions")
def list_questions(iid: str, actor: Actor = Depends(get_actor)):
    try:
        i = catalog.get(iid, actor)
    except catalog.Denied as e:
        raise D(e)
    owner = i.get("owner_sid")
    out = []
    for q in questions.for_item(iid):
        if not questions.visible(q, actor_sid=actor.sid, owner_sid=owner):
            continue
        out.append(questions.public(q, mine=q.get("asker_sid") == actor.sid,
                                    can_answer=bool(actor.sid and actor.sid == owner)))
    return {"questions": out, "can_ask": bool(actor.user and actor.is_adult and catalog.is_public(i)
                                             and i.get("owner_sid") != actor.sid and not i.get("example"))}


@router.post("/showcase/{iid}/questions")
def ask_question(iid: str, body: dict, request: Request, actor: Actor = Depends(get_actor)):
    if not actor.user:
        raise HTTPException(401, "Make a free account to ask the creator a question.")
    if not actor.is_adult:
        raise HTTPException(403, "This account can't ask right now.")
    try:
        i = catalog.get(iid, actor)
    except catalog.Denied as e:
        raise D(e)
    if i.get("example") or i.get("original"):
        raise HTTPException(400, "Questions are for community projects.")
    if not catalog.is_public(i):
        raise HTTPException(403, "Questions are only for public projects.")
    if i.get("owner_sid") == actor.sid:
        raise HTTPException(400, "You can't ask a question on your own project.")
    if not config.TESTING_MODE and not (ratelimit.hit("qask:" + actor.sid, 10, 3600)
                                        and ratelimit.hit("qaskip:" + _ip(request), 40, 3600)):
        raise HTTPException(429, "That's a lot of questions for one hour. Please wait a while.")
    try:
        text = text_in(body.get("text"), questions.TEXT_MAX, "Question")
        text = safety.gate(actor, text, "questions:ask", False)
        rec = questions.ask(iid, sid=actor.sid, uid=actor.user["id"],
                            username=actor.user.get("username"), text=text)
    except safety.ChatBlocked as e:
        return JSONResponse(status_code=e.status, content=e.payload)
    except (ValueError, questions.Bad) as e:
        raise HTTPException(400, str(e))
    return questions.public(rec, mine=True, can_answer=False)


@router.post("/showcase/{iid}/questions/{qid}/answer")
def answer_question(iid: str, qid: str, body: dict, actor: Actor = Depends(get_actor)):
    if not actor.user:
        raise HTTPException(401, "Sign in to answer.")
    try:
        i = catalog.get(iid, actor)
    except catalog.Denied as e:
        raise D(e)
    if i.get("owner_sid") != actor.sid:
        raise HTTPException(403, "Only the project's creator can answer.")
    q = questions.get(qid)
    if not q or q["item_id"] != iid:
        raise HTTPException(404, "Question not found.")
    if not config.TESTING_MODE and not ratelimit.hit("qans:" + actor.sid, 30, 3600):
        raise HTTPException(429, "That's a lot of answers for one hour. Please wait a while.")
    try:
        text = text_in(body.get("text"), questions.ANSWER_MAX, "Answer")
        text = safety.gate(actor, text, "questions:answer", False)
        rec = questions.answer(qid, owner_sid=actor.sid, text=text)
    except safety.ChatBlocked as e:
        return JSONResponse(status_code=e.status, content=e.payload)
    except (ValueError, questions.Bad, KeyError) as e:
        raise HTTPException(400 if not isinstance(e, KeyError) else 404, str(e) if not isinstance(e, KeyError) else "Question not found.")
    return questions.public(rec, mine=False, can_answer=False)


@router.delete("/showcase/{iid}/questions/{qid}")
def delete_question(iid: str, qid: str, actor: Actor = Depends(get_actor)):
    try:
        i = catalog.get(iid, actor)
    except catalog.Denied as e:
        raise D(e)
    ok = questions.remove(qid, sid=actor.sid, is_owner=i.get("owner_sid") == actor.sid)
    if not ok:
        raise HTTPException(404, "Question not found.")
    return {"ok": True}


# ---------------- prize-free themed challenges ----------------
@router.get("/challenges")
def list_challenges(actor: Actor = Depends(get_actor)):
    rows = []
    for c in challenges.list_all():
        row = challenges.public(c)
        row["entered"] = bool(actor.user and challenges.entry_for(c["id"], actor.sid))
        rows.append(row)
    return {"challenges": rows}


@router.get("/challenges/{cid}")
def get_challenge(cid: str, actor: Actor = Depends(get_actor)):
    c = challenges.get(cid)
    if not c:
        raise HTTPException(404, "Challenge not found.")
    ents = challenges.entries(c["id"])
    items = []
    for e in ents:
        try:
            i = catalog.get(e["item_id"], actor)
            if catalog.is_public(i) or i.get("owner_sid") == actor.sid:
                items.append({**catalog.public(i, actor),
                              "entered_at": e["created"], "entry_id": e["id"]})
        except catalog.Denied:
            continue
    return {**challenges.public(c, entry_count=len(ents)), "entries": items,
            "can_enter": bool(actor.user and actor.is_adult and c.get("status") == "open")}


@router.get("/challenges/{cid}/eligible")
def challenge_eligible(cid: str, actor: Actor = Depends(get_actor)):
    """Signed-in maker's own credited remixes, so the enter dialog can list them instead of asking for a URL."""
    c = challenges.get(cid)
    if not c:
        raise HTTPException(404, "Challenge not found.")
    pack = catalog.own_published(actor)
    prior = challenges.entry_for(c["id"], actor.sid) if actor.user else None
    entry = None
    if prior:
        title = ""
        try:
            title = catalog.get(prior["item_id"], actor).get("title") or ""
        except catalog.Denied:
            title = ""
        entry = {"id": prior["id"], "item_id": prior["item_id"], "title": title}
    return {**pack, "challenge_id": c["id"], "status": c.get("status") or "open",
            "already_entered": bool(prior), "entry": entry,
            "can_enter": bool(actor.user and actor.is_adult and c.get("status") == "open" and not prior)}


def _entry_limit(actor: Actor):
    if not config.TESTING_MODE and not ratelimit.hit("chent:" + actor.sid, 10, 3600):
        raise HTTPException(429, "That's a lot of challenge entries for one hour. Please wait a while.")


def _admin_ok(token: str) -> bool:
    if not token or not config.ADMIN_TOKEN:
        return False
    return hmac.compare_digest(token.encode(), config.ADMIN_TOKEN.encode())


@router.delete("/showcase/{iid}")
def remove_showcase(iid: str, actor: Actor = Depends(get_actor), x_admin_token: str = Header("")):
    """Owner or admin. Unpublishes the post. The Studio file stays. Remix credit keeps a stub."""
    try:
        catalog.remove_listing(actor, iid, admin=_admin_ok(x_admin_token))
    except catalog.Denied as e:
        raise D(e)
    challenges.pull_item(iid)
    return {"ok": True, "removed": True,
            "message": "Removed from Showcase. Your saved file stays."}


@router.post("/challenges/{cid}/enter")
def enter_challenge(cid: str, body: dict, request: Request, actor: Actor = Depends(get_actor)):
    if not actor.user:
        raise HTTPException(401, "Make a free account to enter a challenge.")
    if not actor.is_adult:
        raise HTTPException(403, "This account can't enter right now.")
    c = challenges.get(cid)
    if not c:
        raise HTTPException(404, "Challenge not found.")
    if c.get("status") != "open":
        raise HTTPException(400, "This challenge is closed.")
    if challenges.entry_for(c["id"], actor.sid):
        raise HTTPException(400, "You already entered this challenge. One remix per person.")
    item_id = str(body.get("item_id") or "").strip()
    if not item_id:
        raise HTTPException(400, "Pick a project to enter.")
    try:
        item = catalog.get(item_id, actor)
    except catalog.Denied as e:
        raise D(e)
    if item.get("owner_sid") != actor.sid:
        raise HTTPException(403, "You can only enter your own project.")
    if not catalog.is_public(item):
        raise HTTPException(400, "Make the project public before entering.")
    remix_of = item.get("remix_of") or ""
    if not remix_of:
        raise HTTPException(400, "This challenge is for credited remixes. Publish with a Remixed-from link first.")
    _entry_limit(actor)
    try:
        rec = challenges.enter(c["id"], item_id=item_id, sid=actor.sid, uid=actor.user["id"], remix_of=remix_of)
    except KeyError:
        raise HTTPException(404, "Challenge not found.")
    except challenges.Bad as e:
        raise HTTPException(400, str(e))
    return badges.merge(
        {"ok": True, "entry": {"id": rec["id"], "item_id": rec["item_id"],
                               "challenge_id": rec["challenge_id"], "created": rec["created"]},
         "prize_free": True,
         "message": "Entered. Prize-free challenge: no cash, no prizes — just makers helping makers."},
        actor, "challenge")
