"""Community API: identity, Showcase (free projects), personalization, follows, reports, moderation."""
from __future__ import annotations

import io

import trimesh
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from .. import branding, config
from ..community import catalog, classrooms, links, moderation, personalization, privacy, safety
from ..community import identity as idn
from ..community.identity import Actor, get_actor
from ..community.store import USERS
from ..core import ratelimit
from .textcap import ip as _ip, text_in

router = APIRouter(prefix="/api")


def D(e: catalog.Denied):
    return HTTPException(e.status, e.msg)


@router.get("/config")
def get_config():
    return {"product": branding.PRODUCT_NAME, "tagline": branding.TAGLINE, "sections": branding.SECTIONS,
            "showcase_tabs": branding.SHOWCASE_TABS, "max_builds": config.MAX_BUILDS, "group_name": branding.GROUP_NAME,
            "group_name_plural": branding.GROUP_NAME_PLURAL, "chat_block_message": safety.BLOCK_MESSAGE}


# ---------------- identity ----------------
@router.get("/me")
def me(actor: Actor = Depends(get_actor)):
    return idn.public_profile(actor)


def _age_refusal(actor: Actor, lock: bool):
    """Same neutral answer for 'too young' and 'already refused': no threshold, no hint that retrying differs."""
    until = idn.lock_age(actor.sid) if lock else None
    r = JSONResponse(status_code=403, content={"detail": idn.AGE_MESSAGE})
    if until:
        r.set_cookie(idn.AGE_COOKIE, str(until), max_age=config.AGE_LOCK_HOURS * 3600, httponly=True, samesite="lax")
    return r


@router.post("/me/signup")
def signup(request: Request, body: dict, actor: Actor = Depends(get_actor)):
    if not ratelimit.hit("signup:" + _ip(request), config.SIGNUP_ATTEMPTS_PER_HOUR_IP, 3600):
        raise HTTPException(429, "Too many tries from this network. Please wait a while.")
    if not actor.user and idn.age_locked(actor.sid, request.cookies.get(idn.AGE_COOKIE)):
        return _age_refusal(actor, lock=False)
    try:
        name = text_in(body.get("display_name", ""), 40, "Display name")
        safety.filter_only(name, "Display name")
        idn.signup(actor, name, str(body.get("dob", ""))[:12])
    except PermissionError:
        return _age_refusal(actor, lock=True)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return idn.public_profile(Actor(actor.sid, USERS.read()[actor.sid]))


@router.put("/me/links")
def set_links(body: dict, actor: Actor = Depends(get_actor)):
    """'Promote your other accounts': handles are shown as UNVERIFIED link-outs."""
    if not actor.user:
        raise HTTPException(401, "sign up first")
    try:
        cleaned = links.clean(body)
    except (ValueError, AttributeError) as e:
        raise HTTPException(400, str(e))
    USERS.update(lambda d: d[actor.sid].__setitem__("links", cleaned))
    return {"links": cleaned}


@router.get("/users/{uid}")
def public_user(uid: str, actor: Actor = Depends(get_actor)):
    """Profile. Private / followers-only profiles look like 404 to anyone not allowed to see them."""
    _, u = idn.user_by_id(uid)
    if not u:
        if uid in catalog.CREATORS:   # example creators
            return {"id": uid, "display_name": catalog.CREATORS[uid], "followers": None, "can_follow": True, "links": {},
                    "projects": [catalog.public(i, actor) for i in catalog.list_items(actor, "free") if i["creator_id"] == uid]}
        raise HTTPException(404, "unknown user")
    if not privacy.can_view_profile(actor, uid):
        raise HTTPException(404, "unknown user")
    teen = idn.age_of(u) < config.ADULT_AGE
    social = privacy.social_on(u)
    return {"id": u["id"], "display_name": u["display_name"],
            "followers": idn.follower_count(uid) if social else None,   # opted out -> no count at all
            "can_follow": privacy.can_follow(actor, u),
            "following_creator": bool(actor.user and uid in actor.user.get("following", [])),
            "links": {} if teen else u.get("links", {}),   # teens: link-outs never public
            "projects": [catalog.public(i, actor) for i in catalog.list_items(actor, "free") if i["creator_id"] == uid]}


@router.put("/me/privacy")
def set_privacy(body: dict, actor: Actor = Depends(get_actor)):
    try:
        new = privacy.set_privacy(actor, body)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"privacy": new}


@router.get("/me/followers")
def my_followers(actor: Actor = Depends(get_actor)):
    """Only YOU can see your follower list, and only while following is on."""
    if not actor.user:
        raise HTTPException(401, "sign up first")
    if not privacy.social_on(actor.user):
        return {"enabled": False, "followers": []}
    return {"enabled": True, "followers": privacy.followers_of(actor.user["id"])}


@router.get("/me/projects")
def my_projects(actor: Actor = Depends(get_actor)):
    return {"projects": [catalog.public(i, actor) for i in catalog.mine(actor)]}


# ---------------- follows (scaffold: no feed yet) ----------------
@router.post("/follow/{uid}")
def follow(uid: str, actor: Actor = Depends(get_actor)):
    if not actor.user:
        raise HTTPException(401, "sign up to follow creators")
    if uid == actor.user["id"]:
        raise HTTPException(400, "cannot follow yourself")
    if not privacy.social_on(actor.user):
        raise HTTPException(403, "You have opted out of following. Turn it back on in Privacy settings.")
    _, tu = idn.user_by_id(uid)
    if not tu and uid not in catalog.CREATORS:
        raise HTTPException(404, "unknown creator")
    if tu and not privacy.can_follow(actor, tu):
        raise HTTPException(404, "unknown creator")      # opted out / private profile: cannot be followed
    USERS.update(lambda d: d[actor.sid]["following"].append(uid) if uid not in d[actor.sid]["following"] else None)
    return {"following": True}


@router.delete("/follow/{uid}")
def unfollow(uid: str, actor: Actor = Depends(get_actor)):
    if not actor.user:
        raise HTTPException(401, "sign up first")
    USERS.update(lambda d: d[actor.sid]["following"].remove(uid) if uid in d[actor.sid]["following"] else None)
    return {"following": False}


# ---------------- showcase ----------------
@router.get("/showcase")
def showcase(tab: str = "trending", q: str = "", actor: Actor = Depends(get_actor)):
    if tab not in branding.SHOWCASE_TABS:
        raise HTTPException(400, "unknown tab")
    prefs = personalization.get(actor.sid)
    q = q.strip()[:80]
    if q:
        personalization.record_search(actor.sid, q, catalog.known_tags(actor))
    items = catalog.list_items(actor, tab, q, prefs["interests"] if prefs["enabled"] else {})
    out = {"tab": tab, "items": [catalog.public(i, actor) for i in items], "q": q, "result_count": len(items),
           "subtitle": "Newest projects first." if tab == "free" else "",
           "example_notice": "Examples help you see how ZEIM looks. They are not made by real people."}
    if tab == "foryou" and not out["items"]:
        out["hint"] = ("Personalization is off." if not prefs["enabled"] else
                       "Search or open projects to teach For You what you like. Data stays on this server and you can clear it any time.")
    if not items:
        quiet = actor.is_teen or classrooms.is_student(actor.sid)       # no "share one" nudge for teens or class students
        if q:
            out["empty"] = {"text": f'No projects match "{q}". Try a shorter word like "relief" or "lamp", or look in Trending.',
                            "action": {"label": "Clear search", "do": "clear"}}
        elif quiet:
            out["empty"] = {"text": "Nothing here yet. Check back soon.", "action": None}
        elif tab == "foryou" and not prefs["enabled"]:
            out["empty"] = {"text": "For You is off. You can turn it on under My data.", "action": {"label": "Open My data", "do": "mydata"}}
        elif tab == "foryou":
            out["empty"] = {"text": "For You fills up as you look around. Search for something or open a few projects, and ideas will show up here.",
                            "action": {"label": "Look at Trending", "do": "trending"}}
        else:
            out["empty"] = {"text": "No projects here yet. Be the first to share one when you are ready.", "action": {"label": "Go to Studio", "do": "studio"}}
    return out


@router.get("/showcase/{iid}")
def showcase_item(iid: str, actor: Actor = Depends(get_actor)):
    try:
        i = catalog.get(iid, actor)
    except catalog.Denied as e:
        raise D(e)
    personalization.record_view(actor.sid, i["tags"])
    return catalog.public(i, actor)


@router.post("/showcase")
def publish(body: dict, actor: Actor = Depends(get_actor)):
    try:
        title = text_in(body.get("title"), 80, "Title")
        desc = text_in(body.get("description"), 500, "Description")
        raw_tags = body.get("tags") or []
        if not isinstance(raw_tags, list) or len(raw_tags) > 20:
            raise ValueError("Use at most 8 tags.")
        tags = [text_in(t, 30, "Each tag") for t in raw_tags][:8]
        body["title"] = safety.gate(actor, title, "showcase:title")
        body["description"] = safety.gate(actor, desc, "showcase:description")
        body["tags"] = [safety.gate(actor, t, "showcase:tag") for t in tags]
        i = catalog.create_project(actor, title=body.get("title"), description=body.get("description", ""),
                                   tags=body.get("tags") or [], build_id=str(body.get("build_id", ""))[:40],
                                   accept_guidelines=bool(body.get("accept_guidelines")),
                                   visibility=body.get("visibility"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except safety.ChatBlocked as e:
        return JSONResponse(status_code=e.status, content=e.payload)
    except catalog.Denied as e:
        raise D(e)
    return catalog.public(i, actor)


@router.put("/showcase/{iid}/visibility")
def item_visibility(iid: str, body: dict, actor: Actor = Depends(get_actor)):
    """Owner only; takes effect on the very next request by anyone."""
    try:
        return catalog.public(catalog.set_visibility(actor, iid, body.get("visibility", "")), actor)
    except catalog.Denied as e:
        raise D(e)


@router.post("/showcase/{iid}/like")
def like(iid: str, body: dict | None = None, actor: Actor = Depends(get_actor)):
    """Toggle like (or set with {"liked": true|false}). Public projects only. There is deliberately no dislike."""
    try:
        i = catalog.get(iid, actor)
        res = catalog.set_like(i, actor, (body or {}).get("liked"))
    except catalog.Denied as e:
        raise D(e)
    if res["liked"]:
        personalization.record_view(actor.sid, i["tags"], 1.0)
    return res


@router.get("/showcase/{iid}/thumb")
def item_thumb(iid: str, actor: Actor = Depends(get_actor)):
    try:
        p = catalog.thumb_path(catalog.get(iid, actor))
    except catalog.Denied as e:
        raise D(e)
    if not p:
        raise HTTPException(404)
    return FileResponse(p)


@router.get("/showcase/{iid}/files/{name}")
def item_file(iid: str, name: str, actor: Actor = Depends(get_actor)):
    try:
        i = catalog.get(iid, actor)
    except catalog.Denied as e:
        raise D(e)
    p = catalog.file_path(i, name)
    catalog.count_download(i, actor)
    personalization.record_view(actor.sid, i["tags"], 2.0)
    if p:
        return FileResponse(p, filename=name)
    if i.get("example"):  # seed items have no real file: serve a small placeholder cube
        buf = io.BytesIO()
        trimesh.creation.box((20, 20, 5)).export(buf, file_type="stl")
        return Response(buf.getvalue(), media_type="model/stl",
                        headers={"Content-Disposition": 'attachment; filename="example_placeholder.stl"'})
    raise HTTPException(404)


@router.post("/showcase/{iid}/report")
def report(iid: str, body: dict, actor: Actor = Depends(get_actor)):
    try:
        catalog.get(iid, actor)
        return moderation.report(iid, actor.sid, str(body.get("reason", ""))[:40], text_in(body.get("details"), 1000, "Details"))
    except catalog.Denied as e:
        raise D(e)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------------- personalization (view / disable / clear) ----------------
@router.get("/me/data")
def my_data(actor: Actor = Depends(get_actor)):
    p = personalization.get(actor.sid)
    return {**p, "note": "Stored only on this server (data/prefs.json), keyed by your browser session. "
                         "Used only to rank the For You tab."}


@router.delete("/me/data")
def clear_data(actor: Actor = Depends(get_actor)):
    personalization.clear(actor.sid)
    return {"ok": True}


@router.put("/me/personalization")
def set_personalization(body: dict, actor: Actor = Depends(get_actor)):
    personalization.set_enabled(actor.sid, bool(body.get("enabled")))
    return {"enabled": bool(body.get("enabled"))}


# ---------------- moderation (stub; admin token) ----------------
def _admin(token: str):
    if not config.ADMIN_TOKEN:
        raise HTTPException(403, "moderation queue disabled: set PHOTO3D_ADMIN_TOKEN")
    if token != config.ADMIN_TOKEN:
        raise HTTPException(403, "bad admin token")


@router.get("/moderation/queue")
def mod_queue(x_admin_token: str = Header("")):
    _admin(x_admin_token)
    return {"reports": moderation.queue()}


@router.post("/moderation/{rid}/resolve")
def mod_resolve(rid: str, body: dict, x_admin_token: str = Header("")):
    _admin(x_admin_token)
    try:
        out = moderation.resolve(rid, body.get("action", ""))
        if body.get("action") == "hide" and str(out.get("item_id", "")).startswith("fb:"):
            classrooms.hide_feedback(out["item_id"])
        return out
    except KeyError:
        raise HTTPException(404)
    except ValueError as e:
        raise HTTPException(400, str(e))
