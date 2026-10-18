"""Community API: identity, Showcase (free projects), personalization, follows, reports, moderation."""
from __future__ import annotations

import io
import logging

import trimesh
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from .. import branding, config
from ..community import catalog, discovery, links, moderation, personalization, privacy, recovery, safety, usernames
from ..community import identity as idn
from ..community.identity import Actor, get_actor
from ..community.store import USERS, LISTINGS
from ..core import ratelimit
from ..services import credits as _credits
from . import guards
from .textcap import ip as _ip, text_in

log = logging.getLogger("zeim.api")

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
    return {**idn.public_profile(actor), "send": guards.send_caps(request, actor), "hide_mature": catalog.hides_mature(actor)}


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
            usernames.assign_new(actor.sid, user, str(body.get("username") or "")[:40] or None)
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
    svc = getattr(request.app.state, "auth_service", None)
    if svc is not None:                               # a passkey/email session on this browser ends too (else it would sign straight back in)
        if actor.auth_session is not None:
            svc.logout(actor.auth_session)
        if request.cookies.get(svc.cfg.cookie_name):
            r.delete_cookie(svc.cfg.cookie_name, path="/", secure=svc.cfg.secure_cookies, httponly=True, samesite="lax")
    return r


@router.post("/me/recovery-code")
def new_recovery_code(actor: Actor = Depends(get_actor)):
    """Make a fresh recovery code (the old one stops working). Adult accounts only."""
    if not actor.user or not actor.is_adult:
        raise HTTPException(403, "Recovery codes aren't available for this account.")
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
    social = privacy.social_on(u)
    handle = "@" + u["username"] if u.get("username") else "a ZEIM maker"
    return {"id": u["id"], "display_name": handle, "username": u.get("username"),        # public profile: @username only, never the (possibly real) display name
            "followers": idn.follower_count(uid) if social else None,   # opted out -> no count at all
            "following": len(u.get("following", [])) if social else None,
            "can_follow": privacy.can_follow(actor, u),
            "following_creator": bool(actor.user and uid in actor.user.get("following", [])),
            "links": {} if idn.restricted(u) else u.get("links", {}),
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


@router.get("/me/following")
def my_following(actor: Actor = Depends(get_actor)):
    """Only YOU can see who you follow; each row has what the Unfollow button needs."""
    if not actor.user:
        raise HTTPException(401, "sign up first")
    return {"enabled": privacy.social_on(actor.user), "following": privacy.following_of(actor.user)}


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
def showcase(tab: str = "trending", q: str = "", category: str = "", sort: str = "", actor: Actor = Depends(get_actor)):
    guards.showcase_gate(actor)
    if tab not in branding.SHOWCASE_TABS:
        raise HTTPException(400, "unknown tab")
    try:
        discovery.check_sort(sort)                     # newest | likes | printed, or the tab's own order
    except ValueError as e:
        raise HTTPException(400, str(e))
    prefs = personalization.get(actor.sid)
    q = q.strip()[:80]
    if q:
        personalization.record_search(actor.sid, q, catalog.known_tags(actor))
    items = catalog.list_items(actor, tab, q, prefs["interests"] if prefs["enabled"] else {}, category.strip()[:60])
    items = discovery.apply_sort(items, sort)
    out = {"categories": catalog.categories(actor), "category": category.strip()[:60],
           "originals_notice": _originals_notice(),"tab": tab, "items": [catalog.public(i, actor) for i in items], "q": q, "result_count": len(items),
           "subtitle": "Newest projects first." if tab == "free" else "",
           "example_notice": ""}
    if tab == "foryou" and not out["items"]:
        out["hint"] = ("Personalization is off." if not prefs["enabled"] else
                       "Search or open projects to teach For You what you like. Data stays on this server and you can clear it any time.")
    if not items:
        quiet = bool(actor.user) and not actor.is_adult       # no "share one" nudge for an account that can't share
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
    out = catalog.public(i, actor)
    out["related"] = discovery.related(i, actor)      # up to 6 compact summaries (same maker, then same tag)
    return out


@router.post("/showcase")
def publish(body: dict, actor: Actor = Depends(get_actor)):
    build_id = str(body.get("build_id", ""))[:40]
    if build_id:
        from ..services import quarantine
        if quarantine.is_quarantined(build_id):
            raise HTTPException(409, "That project is pending its malware scan and can't be shared yet.")
    try:
        title = text_in(body.get("title"), 80, "Title")
        desc = text_in(body.get("description"), 500, "Description")
        raw_tags = body.get("tags") or []
        if not isinstance(raw_tags, list) or len(raw_tags) > 20:
            raise ValueError("Use at most 8 tags.")
        tags = [text_in(t, 30, "Each tag") for t in raw_tags][:8]
        nsfw = None if body.get("nsfw") is None else safety.parse_nsfw(body.get("nsfw"))     # missing -> 422 from create_project
        body["title"] = safety.gate(actor, title, "showcase:title", bool(nsfw))
        body["description"] = safety.gate(actor, desc, "showcase:description", bool(nsfw))
        body["tags"] = [safety.gate(actor, t, "showcase:tag", bool(nsfw)) for t in tags]
        i = catalog.create_project(actor, title=body.get("title"), description=body.get("description", ""),
                                   tags=body.get("tags") or [], build_id=str(body.get("build_id", ""))[:40],
                                   accept_guidelines=bool(body.get("accept_guidelines")),
                                   visibility=body.get("visibility"), remix_of=str(body.get("remix_of") or "")[:200], nsfw=nsfw,
                                   license_id=body.get("license_id"))
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
        i = catalog.get(iid, actor)
        owner = USERS.read().get(i.get("owner_sid") or "") or {}
        return moderation.report(iid, actor.sid, str(body.get("reason", ""))[:40], text_in(body.get("details"), 1000, "Details"), owner.get("id"),
                                 ip=request.client.host if request.client else "",
                                 user_agent=request.headers.get("user-agent", ""))
    except catalog.Denied as e:
        raise D(e)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/users/{uid}/report")
def report_user(uid: str, request: Request, body: dict, actor: Actor = Depends(get_actor)):
    """Report an ACCOUNT (e.g. reason 'underage_user': ZEIM is 18+ only). Unknown / hidden profiles answer 404."""
    report_limit(request, actor)
    _, u = idn.user_by_id(uid)
    if not u or not privacy.can_view_profile(actor, uid):
        raise HTTPException(404, "unknown user")
    try:
        return moderation.report("user:" + uid, actor.sid, str(body.get("reason", "underage_user"))[:40], text_in(body.get("details"), 1000, "Details"), uid,
                                ip=request.client.host if request.client else "",
                                user_agent=request.headers.get("user-agent", ""))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/moderation/appeal/{item_kind}/{item_id}")
def user_appeal(item_kind: str, item_id: str, body: dict, actor: Actor = Depends(get_actor)):
    """The person a decision was about asks for a second look (Task 6 appeals flow).
    item_kind: 'showcase' or 'user'. Only the affected account can appeal; the report re-enters
    the moderation queue as "appealed" for a moderator to re-decide."""
    guards.showcase_gate(actor)
    if item_kind not in ("showcase", "user") or not item_id.replace(":", "").replace("-", "").isalnum():
        raise HTTPException(400, "unknown appeal target")
    try:
        return moderation.appeal_for_item(("user:" if item_kind == "user" else "") + item_id,
                                         actor.sid, text_in(body.get("text", ""), 1000, "Appeal"))
    except KeyError:
        raise HTTPException(404, "no decided report about this yet")
    except ValueError as e:
        raise HTTPException(400, str(e))
    except PermissionError:
        raise HTTPException(403, "Only the person the decision was about can appeal it.")


@router.post("/report/takedown")
def report_dmca(request: Request, body: dict, actor: Actor = Depends(get_actor)):
    """Formal DMCA takedown notice intake (Task 5). No account needed — rights holders may not be users.
    The notice must carry the elements from /legal/takedown (name, contact, the original work, the ZEIM
    item, the good-faith + accuracy statements, signature ack). It lands in the admin queue as a
    copyright report with the notice attached (admin-only), and the takedown contact is notified
    (email when SMTP is configured; always logged)."""
    report_limit(request, actor)
    for f in ("reporter_name", "reporter_contact", "original_work", "item_ref"):
        if not str(body.get(f) or "").strip():
            raise HTTPException(422, f"A DMCA notice needs: {f}")
    if not (body.get("good_faith") and body.get("accuracy") and body.get("signature")):
        raise HTTPException(422, "The notice needs the good-faith, accuracy and signature statements (see /legal/takedown).")
    item_ref = str(body["item_ref"]).strip()[:200]
    item_id = item_ref.rsplit("/", 1)[-1].split("?")[0].strip()
    if not item_id.isalnum() or not item_id:
        raise HTTPException(422, "item_ref must be the Showcase item's address or id")
    owner = USERS.read().get(next((i.get("owner_sid") for i in LISTINGS.read() if i.get("id") == item_id), "") or "") or {}
    try:
        rep = moderation.report_dmca(item_id, owner.get("id"), body, actor.sid,
                                     ip=request.client.host if request.client else "",
                                     user_agent=request.headers.get("user-agent", ""))
    except ValueError as e:
        raise HTTPException(400, str(e))
    # notify the takedown contact: email when SMTP is configured, always logged
    contact = (_credits.data().get("takedown", {}) or {}).get("contact") or ""
    if contact:
        try:
            import os
            from ..auth.mailer import mailer_from_env
            mailer_from_env(os.environ).send(contact, "ZEIM: DMCA takedown notice",
                                             f"A DMCA notice was filed for showcase item {item_id}. "
                                             f"Review it in the moderation queue (report {rep['id']}).")
        except Exception:
            log.exception("DMCA notice email failed (logged instead)")
    else:
        log.warning("DMCA notice filed for item %s — takedown contact is NOT configured (app/credits.json)", item_id)
    return {"ok": True, "report_id": rep["id"], "status": rep["status"]}


# ---------------- personalization (view / disable / clear) ----------------
def _what_zeim_knows(actor: Actor) -> dict:
    """Plain summary of everything ZEIM holds for this browser session / account (no photo bytes, no EXIF)."""
    from ..services.history import store as _builds
    p = personalization.get(actor.sid)
    builds = [{"id": m["id"], "title": m.get("title"), "mode": m.get("mode"), "kind": m.get("kind", "photo"),
               "created": m.get("created"), "favorite": bool(m.get("favorite")),
               "visibility": m.get("visibility", "private")} for m in _builds.list(actor.sid)]
    shared = [{"id": i["id"], "title": i.get("title"), "visibility": i.get("visibility", "private"),
               "created": i.get("created")} for i in catalog.LISTINGS.read() if i.get("owner_sid") == actor.sid]
    acct = None
    if actor.user:
        acct = {"username": actor.user.get("username"), "display_name": actor.user.get("display_name"),
                "printer": actor.user.get("printer"), "privacy": actor.user.get("privacy"),
                "following_count": len(actor.user.get("following") or [])}
    return {
        "account": acct, "signed_up": bool(actor.user),
        "builds": builds, "builds_count": len(builds),
        "shared": shared, "shared_count": len(shared),
        "personalization": {"enabled": p.get("enabled"), "interests": p.get("interests") or {},
                            "searches": p.get("searches") or []},
        "not_collected": ["email (unless you used passkey/email login)", "phone number", "precise location",
                          "payment info", "ads or trackers", "grades or school records"],
        "note": ("Here is everything ZEIM keeps for you on this server. Photos you uploaded are kept with each build "
                 "until you delete that build (EXIF/GPS is stripped on upload). ZEIM does not sell your data."),
    }


@router.get("/me/data")
def my_data(actor: Actor = Depends(get_actor)):
    """What ZEIM knows about you (live view for the My data dialog)."""
    d = _what_zeim_knows(actor)
    # keep the old personalization keys at the top level so older clients still work
    p = d["personalization"]
    return {**d, "enabled": p["enabled"], "interests": p["interests"], "searches": p["searches"]}


@router.get("/me/export")
def export_my_stuff(actor: Actor = Depends(get_actor)):
    """Download a JSON file of what ZEIM knows about you (metadata only — no photo/model bytes)."""
    import json as _json
    from datetime import datetime, timezone
    body = _what_zeim_knows(actor)
    body["exported_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body["export_note"] = ("Metadata only. To save a model file, open the build and use Send or save. "
                           "This file is for your records; it is not a full backup of every STL.")
    raw = _json.dumps(body, indent=2, ensure_ascii=False).encode("utf-8")
    return Response(content=raw, media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="zeim-my-data.json"',
                             "Cache-Control": "no-store"})


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


@router.put("/me/mature")
def set_mature(body: dict, actor: Actor = Depends(get_actor)):
    """Account setting 'Hide mature content entirely' (default off = NSFW items show as blurred cards)."""
    if not actor.user:
        raise HTTPException(401, "Make a free account to change this setting.")
    on = bool(body.get("hide_mature"))
    USERS.update(lambda d: d[actor.sid].__setitem__("hide_mature", on))
    return {"hide_mature": on}


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
    if item_id.startswith("user:"):
        _, u = idn.user_by_id(item_id[5:])
        return {"kind": "account", "title": "@" + ((u or {}).get("username") or "?"), "text": "", "creator": "@" + ((u or {}).get("username") or "?"),
                "hidden": False, "suspended": bool(u and u.get("suspended"))}
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
    return {"kind": "showcase project", "title": i["title"], "text": (i.get("description") or "")[:300], "creator": catalog.resolve(i)["creator"], "hidden": bool(i["hidden"]), "nsfw": bool(i.get("nsfw")),       # @username via the account id, never the display name
            "thumb": f"/api/moderation/item/{item_id}/thumb" if i.get("has_thumb") else None}


def _originals_notice() -> str:
    from ..community import originals_proof
    n = originals_proof.count_test_printed([i["id"] for i in catalog._all() if i.get("original")])
    head = ("ZEIM Originals are free (CC BY 4.0). Each one is marked Simulated (checked on a computer only) "
            "or Test-printed (a real ZEIM print is logged). ")
    if not n:
        return head + "None has been test-printed yet: treat every file as an untested print."
    return head + f"{n} {'has' if n == 1 else 'have'} been test-printed so far; treat every Simulated file as an untested print."


# ---------------- ZEIM Originals: logged test prints (admin token) ----------------
@router.get("/moderation/originals/prints")
def originals_prints(request: Request, x_admin_token: str = Header("")):
    _admin(x_admin_token, request)
    from ..community import originals_proof
    return {"prints": originals_proof.entries(), "results": originals_proof.RESULTS}


@router.post("/moderation/originals/{item_id}/prints")
def originals_log_print(item_id: str, body: dict, request: Request, x_admin_token: str = Header("")):
    """Log a REAL print of an Original (printer, date, outcome). Only then can it show Test-printed."""
    _admin(x_admin_token, request)
    from ..community import originals_proof
    if not any(i["id"] == item_id and i.get("original") for i in catalog._all()):
        raise HTTPException(404, "That ZEIM Original wasn't found.")
    try:
        e = originals_proof.log_print(item_id, body.get("printer"), str(body.get("printed_on", "")), str(body.get("result", "")),
                                      body.get("logged_by") or "admin", body.get("notes") or "")
    except originals_proof.ProofError as er:
        raise HTTPException(400, str(er))
    import logging
    logging.getLogger("zeim.audit").info("original test print logged: item=%s entry=%s result=%s", item_id, e["id"], e["result"])
    return {"entry": e, "proof": originals_proof.proof(item_id)}


@router.post("/moderation/originals/prints/{entry_id}/retract")
def originals_retract_print(entry_id: str, request: Request, body: dict | None = None, x_admin_token: str = Header("")):
    """A wrong log entry is marked retracted (kept for the record), never deleted."""
    _admin(x_admin_token, request)
    from ..community import originals_proof
    try:
        e = originals_proof.retract(entry_id, (body or {}).get("reason") or "", (body or {}).get("by") or "admin")
    except KeyError:
        raise HTTPException(404, "That print log entry wasn't found.")
    import logging
    logging.getLogger("zeim.audit").info("original test print retracted: entry=%s", entry_id)
    return {"entry": e, "proof": originals_proof.proof(e["item_id"])}


@router.get("/moderation/queue")
def mod_queue(request: Request, x_admin_token: str = Header("")):
    """Open reports, OLDEST FIRST, with a preview of the item and the age of the oldest one. (The reporter's session id is never sent.)"""
    _admin(x_admin_token, request)
    q = sorted(moderation.queue(), key=lambda r: r["created"])
    return {"reports": [{k: v for k, v in r.items() if k != "reporter"} | {"preview": _preview(r["item_id"])} for r in q],
            "oldest_open_age_s": moderation.oldest_open_age_s(), "pending_prints": _pending_prints()}


@router.get("/moderation/audit")
def mod_audit(request: Request, x_admin_token: str = Header("")):
    """Persistent moderation audit trail (newest first): every report, decision, appeal, preservation
    and escalation, with timestamps. Admin only."""
    _admin(x_admin_token, request)
    return {"entries": moderation.audit_trail()}


@router.get("/admin/metrics")
def admin_metrics(request: Request, x_admin_token: str = Header("")):
    """Operational metrics for monitoring, behind the admin token (/healthz stays liveness-only).
    Slicing is synchronous by design (each request slices inline, capped by RLIMIT_AS + timeout) —
    there is no queue, so there is no queue depth; slice failures appear in the app logs."""
    _admin(x_admin_token, request)
    from .. import config
    from ..services import quarantine, retention
    from ..services.history import store
    q = moderation.queue()
    return {
        "moderation": {"open_reports": len(q), "oldest_open_age_s": moderation.oldest_open_age_s()},
        "quarantined_builds": sum(1 for m in store.list() if m.get("quarantined")),
        "storage": {"mode": config.STORAGE_MODE},
        "disk_free_mb": round(retention.free_bytes() / (1024 * 1024)),
    }


@router.post("/moderation/report/{report_id}/preserve")
def mod_preserve(report_id: str, request: Request, x_admin_token: str = Header("")):
    """Securely preserve the reported content + context for possible law-enforcement reporting
    (files land in DATA/preservation/<report_id>/, mode 700, never served). Admin only."""
    _admin(x_admin_token, request)
    try:
        return moderation.preserve(report_id)
    except KeyError:
        raise HTTPException(404, "unknown report")


@router.post("/moderation/release-quarantine/{bid}")
def mod_release_quarantine(bid: str, request: Request, x_admin_token: str = Header("")):
    """Lift an upload-quarantine hold by decision (audited). Admin only — the automatic path
    (scanner back + clean re-scan) needs no one."""
    _admin(x_admin_token, request)
    from ..services import quarantine
    try:
        return quarantine.release(bid)
    except KeyError:
        raise HTTPException(404, "build is not quarantined")


@router.post("/moderation/report/{report_id}/escalate-ncmec")
def mod_escalate(report_id: str, request: Request, body: dict | None = None, x_admin_token: str = Header("")):
    """Mark a report as escalated for NCMEC CyberTipline reporting (requires preservation first).
    This NEVER auto-submits: a human files the report per docs/legal/ncmec-procedure.md. Admin only."""
    _admin(x_admin_token, request)
    try:
        return moderation.escalate_ncmec(report_id, (body or {}).get("note", ""))
    except KeyError:
        raise HTTPException(404, "unknown report")
    except ValueError as e:
        raise HTTPException(400, str(e))


def _pending_prints():
    from ..community import social
    return [{"id": p["id"], "item_id": p["item_id"], "caption": p.get("caption", ""), "by": "@" + (p.get("username") or "?"), "created": p["created"],
             "nsfw": bool(p.get("nsfw")), "thumb": f"/api/moderation/item/print:{p['id']}/thumb"} for p in social.pending()]


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


@router.post("/moderation/item/{iid}/nsfw")
def mod_nsfw(iid: str, body: dict, request: Request, x_admin_token: str = Header("")):
    """Moderator flips the mature tag on a project or print photo ("print:<id>") without a report."""
    _admin(x_admin_token, request)
    on = bool(body.get("nsfw"))
    if not moderation.set_nsfw(iid, on):
        raise HTTPException(404)
    return {"id": iid, "nsfw": on}


@router.post("/moderation/users/{uid}/suspend")
def mod_suspend(uid: str, request: Request, body: dict | None = None, x_admin_token: str = Header("")):
    _admin(x_admin_token, request)
    if not moderation.suspend(uid, str((body or {}).get("why", "moderator"))):
        raise HTTPException(404)
    return {"ok": True, "suspended": True}


@router.post("/moderation/users/{uid}/unsuspend")
def mod_unsuspend(uid: str, request: Request, x_admin_token: str = Header("")):
    _admin(x_admin_token, request)
    moderation.unsuspend(uid)
    return {"ok": True, "suspended": False}
