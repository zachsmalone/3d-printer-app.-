"""Community extras: search history, favorites, follow counts, 'I printed this' photos. No DMs, no comments."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from .. import config
from ..community import catalog, moderation, personalization, privacy, safety, social
from ..community import identity as idn
from ..community.identity import Actor, get_actor
from ..community.store import PREFS, USERS
from ..core import imagesafe, ratelimit
from .textcap import ip as _ip, text_in

router = APIRouter(prefix="/api")
MAX_PRINT_PHOTO = 25 * 2**20


# ---------------- search history (Showcase) ----------------
@router.get("/me/searches")
def my_searches(actor: Actor = Depends(get_actor)):
    p = personalization.get(actor.sid)
    return {"searches": p["searches"][:10], "enabled": p["enabled"]}


@router.delete("/me/searches")
def clear_searches(actor: Actor = Depends(get_actor)):
    """'Clear history' really deletes: the stored list is removed from data/prefs.json (not hidden, not flagged)."""
    def f(d):
        if actor.sid in d:
            d[actor.sid]["searches"] = []
    PREFS.update(f)
    return {"searches": []}


@router.post("/me/searches/remove")
def remove_search(body: dict, actor: Actor = Depends(get_actor)):
    q = str(body.get("q", ""))[:80]

    def f(d):
        if actor.sid in d:
            d[actor.sid]["searches"] = [s for s in d[actor.sid].get("searches", []) if s != q]
    PREFS.update(f)
    return my_searches(actor)


# ---------------- favorites ----------------
@router.post("/showcase/{iid}/favorite")
def favorite(iid: str, body: dict | None = None, actor: Actor = Depends(get_actor)):
    """Save / unsave to my private Favorites list. {"favorite": bool}; no body toggles."""
    try:
        i = catalog.get(iid, actor)
    except catalog.Denied as e:
        raise HTTPException(e.status, e.msg)
    if not actor.user:
        raise HTTPException(401, "Make a free account to save favorites.")
    if not ratelimit.hit("fav:" + actor.sid, 240, 3600):
        raise HTTPException(429, "That's a lot of taps. Please wait a little.")
    want = (body or {}).get("favorite")
    want = (not social.is_fav(actor.sid, iid)) if want is None else bool(want)
    social.set_fav(actor.sid, iid, want)
    if want:
        personalization.record_view(actor.sid, i["tags"], 1.0)
    return {"favorite": want}


@router.get("/me/favorites")
def my_favorites(actor: Actor = Depends(get_actor)):
    if not actor.user:
        return {"items": []}
    out = []
    for iid in social.favorites(actor.sid):
        try:
            out.append(catalog.public(catalog.get(iid, actor), actor))
        except catalog.Denied:
            continue          # gone, hidden or made private since: silently skipped (the id stays so it comes back if restored)
    return {"items": out}


# ---------------- follow counts ----------------
def following_count(u: dict) -> int:
    return len(u.get("following", []))


@router.get("/users/{uid}/counts")
def user_counts(uid: str, actor: Actor = Depends(get_actor)):
    _, u = idn.user_by_id(uid)
    if not u or not privacy.can_view_profile(actor, uid):
        raise HTTPException(404, "unknown user")
    if not privacy.social_on(u):
        return {"followers": None, "following": None}
    return {"followers": idn.follower_count(uid), "following": following_count(u)}


# ---------------- "I printed this" photos ----------------
def _print_public(p: dict, actor: Actor) -> dict:
    users = USERS.read()
    tu = next((u for u in users.values() if u.get("id") == p["uid"]), None)
    name = (tu or {}).get("username") or p.get("username")
    return {"id": p["id"], "url": f"/api/prints/{p['id']}/photo", "caption": p.get("caption", ""),
            "by": "@" + name if name else "a ZEIM maker", "created": p["created"], "mine": p["owner_sid"] == actor.sid,
            "status": social.status(p), "pending": social.status(p) != "approved"}


@router.get("/showcase/{iid}/prints")
def list_prints(iid: str, actor: Actor = Depends(get_actor)):
    try:
        catalog.get(iid, actor)
    except catalog.Denied as e:
        raise HTTPException(e.status, e.msg)
    return {"prints": [_print_public(p, actor) for p in social.prints_for(iid, actor.sid)]}


@router.post("/showcase/{iid}/prints")
def add_print(iid: str, request: Request, actor: Actor = Depends(get_actor), photo: UploadFile = File(...),
              caption: str = Form(""), photo_ack: bool = Form(False)):
    """Same pipeline as every other photo: permission box (CR-5), content sniffing, EXIF/GPS stripped by re-encoding, size caps;
    the caption goes through the chat filter; the image-moderation hook runs (default: needs human review, never auto-approves);
    every photo can be reported (minor_safety hides it at once) and reviewed in the queue."""
    if not actor.user:
        raise HTTPException(401, "Make a free account to share a photo of your print.")
    if not actor.is_adult:
        raise HTTPException(403, "This account can't share right now.")
    try:
        i = catalog.get(iid, actor)
    except catalog.Denied as e:
        raise HTTPException(e.status, e.msg)
    if not catalog.is_public(i):
        raise HTTPException(403, "Print photos can only be added to public projects.")
    if not (ratelimit.hit("printphoto:" + actor.sid, 10, 3600) and ratelimit.hit("printphotoip:" + _ip(request), 40, 3600)):
        raise HTTPException(429, "That's a lot of photos for one hour. Please wait a while.")
    data = photo.file.read(MAX_PRINT_PHOTO + 1)
    if len(data) > MAX_PRINT_PHOTO:
        raise HTTPException(413, "Photo too large (max 25 MB).")
    try:
        cap = text_in(caption, 140, "Caption")
        cap = safety.gate(actor, cap, "prints:caption") if cap else ""
        ack = imagesafe.check_ack(data, photo_ack)
        clean, ext, _ = imagesafe.sanitize(data)
    except imagesafe.ImageRefused as e:
        raise HTTPException(415, str(e))
    except safety.ChatBlocked as e:
        return JSONResponse(status_code=e.status, content=e.payload)
    except ValueError as e:
        raise HTTPException(400, str(e))
    rec = social.add_print(iid, actor.sid, actor.user["id"], actor.user.get("username"), clean, ext, cap, ack)
    return _print_public(rec, actor)


def _visible_print(pid: str, actor: Actor) -> dict:
    p = social.get_print(pid)
    if not p or social.mod_key(pid) in set(moderation.MODERATION.read()["hidden"]) or not social.visible_to(p, actor.sid):
        raise HTTPException(404)
    try:
        catalog.get(p["item_id"], actor)
    except catalog.Denied:
        raise HTTPException(404)
    return p


@router.get("/prints/{pid}/photo")
def print_photo(pid: str, actor: Actor = Depends(get_actor)):
    f = social.print_path(_visible_print(pid, actor))
    if not f:
        raise HTTPException(404)
    return FileResponse(f, headers={"Cache-Control": "private, max-age=300"})


@router.delete("/prints/{pid}")
def delete_print(pid: str, actor: Actor = Depends(get_actor)):
    if not social.delete_print(pid, actor.sid):
        raise HTTPException(404)
    return {"ok": True}


@router.post("/prints/{pid}/report")
def report_print(pid: str, request: Request, body: dict, actor: Actor = Depends(get_actor)):
    from .community import report_limit
    report_limit(request, actor)
    _visible_print(pid, actor)
    try:
        p = social.get_print(pid) or {}
        return moderation.report(social.mod_key(pid), actor.sid, str(body.get("reason", ""))[:40], text_in(body.get("details"), 1000, "Details"), p.get("uid"))
    except ValueError as e:
        raise HTTPException(400, str(e))
