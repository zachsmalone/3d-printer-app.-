"""Community API: identity, Showcase (free projects), personalization, follows, reports, moderation."""
from __future__ import annotations

import io

import trimesh
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from .. import branding, config
from ..community import catalog, links, moderation, personalization, privacy, recovery, safety, usernames
from ..community import identity as idn
from ..community.identity import Actor, get_actor
from ..community.store import USERS
from ..core import ratelimit
from . import guards
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
def me(request: Request, actor: Actor = Depends(get_actor)):
    return {**idn.public_profile(actor), "send": guards.send_caps(request, actor)}


def _age_refusal(actor: Actor, lock: bool, ip: str = "", request: Request | None = None):
    """Same neutral answer for 'too young' and 'already refused': no threshold, no hint that retrying differs."""
    until = idn.lock_age(actor.sid, ip) if lock else None
    r = JSONResponse(status_code=403, content={"detail": idn.AGE_MESSAGE})
    if until:
        r.set_cookie(idn.AGE_COOKIE, str(until), max_age=config.AGE_LOCK_HOURS * 3600, **(idn.cookie_args(request) if request else {"httponly": True, "samesite": "lax"}))
    return r


@router.post("/me/signup")
def signup(request: Request, body: dict, actor: Actor = Depends(get_actor)):
    if not ratelimit.hit("signup:" + _ip(request), config.SIGNUP_ATTEMPTS_PER_HOUR_IP, 3600):
        raise HTTPException(429, "Too many tries from this network. Please wait a while.")
    if not actor.user and idn.age_locked(actor.sid, request.cookies.get(idn.AGE_COOKIE), _ip(request)):
        return _age_refusal(actor, lock=False, request=request)
    try:
        name = text_in(body.get("display_name", ""), 40, "Display name")
        safety.filter_only(name, "Display name")
        user = idn.signup(actor, name, str(body.get("dob", ""))[:12])
        try:
            usernames.assign_new(actor.sid, user, str(body.get("username") or "")[:40] or None, minor=idn.age_of(user) < config.ADULT_AGE)
        except usernames.UsernameError as e:
            USERS.update(lambda d: d.pop(actor.sid, None))          # nothing is kept from a sign-up that did not complete
            raise HTTPException(400, str(e))
    except PermissionError:
        return _age_refusal(actor, lock=True, ip=_ip(request), request=request)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if body.get("printer_id"):                              # optional printer + nozzle chosen on the sign-up form
        from app.api.printsetup import save_pref
        from app.services.print_setup import SetupError
        try:
            save_pref(actor.sid, body.get("printer_id"), body.get("nozzle"))
        except SetupError:
            pass                                            # never fail a sign-up over an optional choice
    me_now = Actor(actor.sid, USERS.read()[actor.sid])
    out = idn.public_profile(me_now)
    if me_now.is_adult:                                     # CR-15: shown ONCE, only a hash is kept
        out["recovery_code"] = recovery.issue(actor.sid)
        out["recovery"] = {"has_code": True, "issued": USERS.read()[actor.sid]["recovery_issued"]}
    return out


@router.put("/me/username")
def set_username(request: Request, body: dict, actor: Actor = Depends(get_actor)):
    """Change my username. Server-enforced: 3-20 chars, unique ignoring case, passes the chat filter, no email/phone-like text."""
    if not actor.user:
        raise HTTPException(401, "Create an account first.")
    if not ratelimit.hit("username:" + actor.sid, 20, 3600) or not ratelimit.hit("usernameip:" + _ip(request), 200, 3600):
        raise HTTPException(429, "Too many tries. Please wait a while.")
    try:
        return {"username": usernames.change(actor.sid, str(body.get("username", ""))[:60])}
    except usernames.UsernameWait as e:
        raise HTTPException(429, str(e))
    except usernames.UsernameError as e:
        raise HTTPException(409 if "taken" in str(e) else 400, str(e))


@router.post("/me/username/suggest")
def suggest_username(actor: Actor = Depends(get_actor)):
    if not actor.user:
        raise HTTPException(401, "Create an account first.")
    if not ratelimit.hit("usersuggest:" + actor.sid, 60, 3600):
        raise HTTPException(429, "Too many tries. Please wait a while.")
    return {"suggestions": usernames.suggestions()}


@router.post("/me/recover")
def recover_account(request: Request, body: dict, actor: Actor = Depends(get_actor)):
    """Get an adult account back in a new browser with its recovery code (CR-15). The old browser loses it."""
    try:
        user, new_code = recovery.recover(actor, str(body.get("code", ""))[:60], _ip(request))
    except recovery.Locked:
        raise HTTPException(429, "Too many wrong codes. Please wait ten minutes, then try again.")
    except KeyError:
        raise HTTPException(404, "That code didn't work. Check it and try again.")
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {**idn.public_profile(Actor(actor.sid, user)), "recovery_code": new_code}


@router.post("/me/signout")
def signout(request: Request, actor: Actor = Depends(get_actor)):
    """Sign out of THIS browser: it gets a brand-new empty session. The account itself is kept on the server; an adult gets back in with their
    recovery code (POST /me/recover). There are no passwords yet, so the page tells people that before they press it."""
    if not actor.user:
        raise HTTPException(400, "You're not signed in.")
    import logging, secrets as _s
    logging.getLogger("zeim.audit").info("signout: account=%s", actor.user.get("id"))
    r = JSONResponse({"signed_out": True})
    r.set_cookie(idn.COOKIE, _s.token_urlsafe(24), max_age=3600 * 24 * 365, **idn.cookie_args(request))
    return r


@router.post("/me/recovery-code")
def new_recovery_code(actor: Actor = Depends(get_actor)):
    """Make a fresh recovery code (the old one stops working). Adult accounts only."""
    if not actor.user or not actor.is_adult:
        raise HTTPException(403, "Recovery codes are for adult accounts.")
    return {"recovery_code": recovery.issue(actor.sid)}


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
    guards.showcase_gate(actor)
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
    handle = "@" + u["username"] if u.get("username") else "a ZEIM maker"
    return {"id": u["id"], "display_name": handle, "username": u.get("username"),        # public profile: @username only, never the (possibly real) display name
            "followers": idn.follower_count(uid) if social else None,   # opted out -> no count at all
            "following": len(u.get("following", [])) if social else None,
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
def showcase(tab: str = "trending", q: str = "", category: str = "", actor: Actor = Depends(get_actor)):
    guards.showcase_gate(actor)
    if tab not in branding.SHOWCASE_TABS:
        raise HTTPException(400, "unknown tab")
    prefs = personalization.get(actor.sid)
    q = q.strip()[:80]
    if q:
        personalization.record_search(actor.sid, q, catalog.known_tags(actor))
    items = catalog.list_items(actor, tab, q, prefs["interests"] if prefs["enabled"] else {}, category.strip()[:60])
    out = {"categories": catalog.categories(actor), "category": category.strip()[:60],
           "originals_notice": "ZEIM Originals are free (CC BY 4.0). None has been test-printed yet: treat every file as an untested print.","tab": tab, "items": [catalog.public(i, actor) for i in items], "q": q, "result_count": len(items),
           "subtitle": "Newest projects first." if tab == "free" else "",
           "example_notice": ""}
    if tab == "foryou" and not out["items"]:
        out["hint"] = ("Personalization is off." if not prefs["enabled"] else
                       "Search or open projects to teach For You what you like. Data stays on this server and you can clear it any time.")
    if not items:
        quiet = actor.is_teen       # no "share one" nudge for teens
        if q:
            out["empty"] = {"text": f'No projects match "{q}". Try a shorter word like "relief" or "lamp", or look in Trending.',
                            "action": {"label": "Clear search", "do": "clear"}}
        elif tab == "following":
            out["empty"] = ({"text": "Follow makers you like and their new projects show up here. Open a project and tap Follow.",
                             "action": {"label": "Look at Trending", "do": "trending"}} if actor.user else
                            {"text": "Make a free account to follow makers. Their new projects then show up here.", "action": None})
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
    guards.showcase_gate(actor)
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
                                   visibility=body.get("visibility"), remix_of=str(body.get("remix_of") or "")[:200])
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
    guards.showcase_gate(actor, likes=True)
    """Toggle like (or set with {"liked": true|false}). Public projects only. There is deliberately no dislike."""
    try:
        i = catalog.get(iid, actor)                      # private / followers-only stay 404 for everyone not allowed to see them
        if not actor.user:
            raise HTTPException(401, "Make a free account to nozzle projects.")      # signed-out visitors can look, not nozzle 
        res = catalog.set_like(i, actor, (body or {}).get("liked"))
    except catalog.Denied as e:
        raise D(e)
    if res["liked"]:
        personalization.record_view(actor.sid, i["tags"], 1.0)
    return res


@router.get("/showcase/{iid}/thumb")
def item_thumb(iid: str, actor: Actor = Depends(get_actor)):
    guards.showcase_gate(actor)
    try:
        p = catalog.thumb_path(catalog.get(iid, actor))
    except catalog.Denied as e:
        raise D(e)
    if not p:
        raise HTTPException(404)
    return FileResponse(p)


@router.get("/showcase/{iid}/files/{name}")
def item_file(iid: str, name: str, actor: Actor = Depends(get_actor)):
    guards.showcase_gate(actor)
    try:
        i = catalog.get(iid, actor)
    except catalog.Denied as e:
        raise D(e)
    p = catalog.file_path(i, name)
    if not p:
        raise HTTPException(404, "No model yet.")
    catalog.count_download(i, actor)
    personalization.record_view(actor.sid, i["tags"], 2.0)
    return FileResponse(p, filename=name)


def report_limit(request: Request, actor: Actor):
    """CR-11 b: at most REPORT_LIMIT_PER_MIN reports a minute per browser session (and a larger cap per network address)."""
    if not (ratelimit.hit("report:" + actor.sid, config.REPORT_LIMIT_PER_MIN, 60) and ratelimit.hit("reportip:" + _ip(request), config.REPORT_LIMIT_PER_MIN_IP, 60)):
        raise HTTPException(429, "That's a lot of reports in one minute. Please wait a little, then try again.")


@router.post("/showcase/{iid}/report")
def report(iid: str, request: Request, body: dict, actor: Actor = Depends(get_actor)):
    report_limit(request, actor)
    guards.showcase_gate(actor)
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


@router.delete("/me/builds")
def delete_everything_i_made(actor: Actor = Depends(get_actor)):
    """'Delete everything I made': every build / Edit project (starred ones too, photos included) and every project this person shared to the Showcase."""
    import shutil as _sh
    from ..community.store import LISTINGS as _L
    from ..community import ownership
    builds = ownership.purge_builds(actor.sid)
    mine = [i["id"] for i in _L.read() if i.get("owner_sid") == actor.sid]
    for pid in mine:
        _sh.rmtree(catalog.LDIR / pid, ignore_errors=True)
    _L.update(lambda l: l.__setitem__(slice(None), [i for i in l if i.get("owner_sid") != actor.sid]))
    return {"ok": True, "builds": builds, "shared": len(mine)}


@router.put("/me/personalization")
def set_personalization(body: dict, actor: Actor = Depends(get_actor)):
    personalization.set_enabled(actor.sid, bool(body.get("enabled")))
    return {"enabled": bool(body.get("enabled"))}


# ---------------- moderation (stub; admin token) ----------------
def _admin(token: str, request: Request | None = None):
    import hmac
    if not config.ADMIN_TOKEN:
        raise HTTPException(403, "moderation queue disabled: set PHOTO3D_ADMIN_TOKEN")
    key = "admintok:" + (_ip(request) if request else "-")
    if ratelimit.count(key, 600) >= config.ADMIN_FAIL_LIMIT:            # same guess limiter as the other admin routes
        raise HTTPException(429, "Too many wrong admin tokens from this address. Try again in a few minutes.")
    if not hmac.compare_digest((token or "").encode(), config.ADMIN_TOKEN.encode()):
        ratelimit.hit(key, 10 ** 6, 600)
        raise HTTPException(403, "bad admin token")


def _preview(item_id: str) -> dict:
    if item_id.startswith("print:"):
        from ..community import social
        p = social.get_print(item_id[6:])
        if not p:
            return {"kind": "unknown", "title": "(photo no longer exists)", "text": ""}
        return {"kind": "print photo", "title": "I printed this photo", "text": p.get("caption", ""), "creator": "@" + (p.get("username") or "?"),
                "hidden": item_id in moderation.MODERATION.read()["hidden"], "thumb": f"/api/moderation/item/{item_id}/thumb"}
    i = next((x for x in catalog._all() if x["id"] == item_id), None)
    if not i:
        return {"kind": "unknown", "title": "(item no longer exists)", "text": ""}
    return {"kind": "showcase project", "title": i["title"], "text": (i.get("description") or "")[:300], "creator": catalog.resolve(i)["creator"], "hidden": bool(i["hidden"]),       # @username via the account id, never the display name
            "thumb": f"/api/moderation/item/{item_id}/thumb" if i.get("has_thumb") else None}


@router.get("/moderation/queue")
def mod_queue(request: Request, x_admin_token: str = Header("")):
    """Open reports, OLDEST FIRST, with a preview of the item and the age of the oldest one. (The reporter's session id is never sent.)"""
    _admin(x_admin_token, request)
    q = sorted(moderation.queue(), key=lambda r: r["created"])
    return {"reports": [{k: v for k, v in r.items() if k != "reporter"} | {"preview": _preview(r["item_id"])} for r in q],
            "oldest_open_age_s": moderation.oldest_open_age_s(), "pending_prints": _pending_prints()}


def _pending_prints():
    from ..community import social
    return [{"id": p["id"], "item_id": p["item_id"], "caption": p.get("caption", ""), "by": "@" + (p.get("username") or "?"), "created": p["created"],
             "thumb": f"/api/moderation/item/print:{p['id']}/thumb"} for p in social.pending()]


@router.post("/moderation/prints/{pid}/{action}")
def mod_print(pid: str, action: str, request: Request, x_admin_token: str = Header("")):
    """Review an 'I printed this' photo: approve (shows in the gallery, counts for Trending) or reject (record and file deleted)."""
    _admin(x_admin_token, request)
    from ..community import social
    import logging
    if action not in ("approve", "reject"):
        raise HTTPException(400, "action must be approve | reject")
    try:
        social.approve(pid) if action == "approve" else social.reject(pid)
    except KeyError:
        raise HTTPException(404)
    logging.getLogger("zeim.audit").info("print photo %s: %s", action, pid)
    return {"id": pid, "status": "approved" if action == "approve" else "deleted"}


@router.get("/moderation/item/{iid}/thumb")
def mod_thumb(iid: str, request: Request, x_admin_token: str = Header("")):
    _admin(x_admin_token, request)
    if iid.startswith("print:"):
        from ..community import social
        pr = social.get_print(iid[6:])
        p = social.print_path(pr) if pr else None
    else:
        i = next((x for x in catalog._all() if x["id"] == iid), None)
        p = catalog.thumb_path(i) if i else None
    if not p:
        raise HTTPException(404)
    return FileResponse(p, headers={"Cache-Control": "no-store"})


@router.post("/moderation/{rid}/resolve")
def mod_resolve(rid: str, body: dict, request: Request, x_admin_token: str = Header("")):
    _admin(x_admin_token, request)
    try:
        out = moderation.resolve(rid, body.get("action", ""))
        return out
    except KeyError:
        raise HTTPException(404)
    except ValueError as e:
        raise HTTPException(400, str(e))
