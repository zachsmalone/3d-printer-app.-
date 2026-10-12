"""Education center + classrooms + public shareable pages."""
from __future__ import annotations

from html import escape

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from .. import branding
from ..config import STATIC as STATIC_DIR
from ..community import catalog, classrooms, education, moderation, privacy, safety
from ..services import credits, settings
from . import guards
from .community import report_limit
from .textcap import ip as ip_of
from ..community import identity as idn
from ..community.identity import Actor, get_actor

router = APIRouter(prefix="/api")
pages = APIRouter()


@router.get("/learn/lessons")
def lessons(actor: Actor = Depends(get_actor)):
    cls = classrooms.student_view(actor.sid)
    return {"lessons": education.catalog(actor.sid), "classroom": cls, "assigned": cls["assigned"] if cls else [],
            "badges": [l["badge"] for l in education.catalog(actor.sid) if l["badge"]]}


@router.get("/learn/lessons/{lid}")
def lesson(lid: str, actor: Actor = Depends(get_actor)):
    l = education.lesson(actor.sid, lid)
    if not l:
        raise HTTPException(404)
    l["share_url"] = f"/l/{lid}"
    return l


@router.post("/learn/lessons/{lid}/steps/{idx}")
def step(lid: str, idx: int, body: dict, actor: Actor = Depends(get_actor)):
    try:
        education.mark_step(actor.sid, lid, idx, bool(body.get("done", True)))
    except KeyError:
        raise HTTPException(404)
    return education.lesson(actor.sid, lid)["progress"]


@router.post("/learn/lessons/{lid}/quiz")
def quiz(lid: str, body: dict, actor: Actor = Depends(get_actor)):
    try:
        return education.answer_quiz(actor.sid, lid, int(body.get("choice", -1)))
    except KeyError:
        raise HTTPException(404)


@router.delete("/learn/progress")
def reset_progress(actor: Actor = Depends(get_actor)):
    education.reset(actor.sid)
    return {"ok": True}


# ---- classrooms ----
def _blocked(e: safety.ChatBlocked):
    return JSONResponse(status_code=e.status, content=e.payload)


@router.post("/classrooms")
def create_room(body: dict, actor: Actor = Depends(get_actor)):
    try:
        return classrooms.create(actor, body.get("name", ""), body.get("password", ""))
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/classrooms")
def my_rooms(actor: Actor = Depends(get_actor)):
    return {"rooms": classrooms.teacher_rooms(actor)}


@router.get("/classrooms/{code}/qr.svg")
def room_qr(code: str, request: Request, actor: Actor = Depends(get_actor)):
    """Teacher only. Encodes the join LINK (class code only - never the password)."""
    try:
        role, room = classrooms.membership(actor, code)
    except KeyError:
        raise HTTPException(404)
    if role != "teacher":
        raise HTTPException(404)
    base = settings.trusted_base_url(request)
    if not base:
        raise HTTPException(409, "Set the site's public address (Settings, or PHOTO3D_PUBLIC_BASE_URL) before making a QR code.")
    return Response(classrooms.qr_svg(base, room["code"]), media_type="image/svg+xml")


@router.post("/classrooms/join")
def join_room(request: Request, response: Response, body: dict, actor: Actor = Depends(get_actor)):
    try:
        out = classrooms.join(actor.sid, body.get("code", ""), body.get("nickname", ""), body.get("password", ""),
                              ip=ip_of(request), seat_code=body.get("seat_code", ""))
        if body.get("shared_computer") is True:
            idn.session_only_cookie(request, response, actor.sid)     # CR-4: forgotten when the browser closes
        return out
    except KeyError:
        raise HTTPException(404, "Wrong class code or password")
    except PermissionError as e:
        raise HTTPException(429, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/classrooms/{code}/send")
def class_send_switch(code: str, body: dict, actor: Actor = Depends(get_actor)):
    """Teacher-only. Turning ON needs an explicit confirm (the page shows the warning dialog first)."""
    on = body.get("enabled") is True
    if on and body.get("confirm") is not True:
        raise HTTPException(400, "Please confirm that you want to turn this on.")
    try:
        return classrooms.set_send(actor, code, on)
    except KeyError:
        raise HTTPException(404)


@router.put("/classrooms/{code}/showcase")
def class_showcase_switch(code: str, body: dict, actor: Actor = Depends(get_actor)):
    """Teacher-only. Showcase is OFF for a class's students unless this is on; likes are a second switch (CR-3)."""
    try:
        return classrooms.set_showcase(actor, code, enabled=body.get("enabled") if "enabled" in body else None,
                                       likes=body.get("likes") if "likes" in body else None)
    except KeyError:
        raise HTTPException(404)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/classrooms/{code}/students/{who}/reset")
def reset_seat(code: str, who: str, actor: Actor = Depends(get_actor)):
    """Teacher-only 'Reset seat' (CR-4). Returns a ONE-TIME seat code to read out to that student; the old browser loses the seat."""
    try:
        return classrooms.reset_seat(actor, code, who)
    except KeyError:
        raise HTTPException(404)


@router.delete("/me/class-data")
def delete_my_class_data(actor: Actor = Depends(get_actor)):
    """A class student erases their builds (with photos), lesson progress and projects sent to the class (CR-2)."""
    try:
        return classrooms.delete_my_data(actor.sid)
    except KeyError:
        raise HTTPException(404, "You are not in a class.")


@router.post("/classrooms/{code}/unlock-joins")
def unlock_joins(code: str, actor: Actor = Depends(get_actor)):
    try:
        classrooms.unlock_joins(actor, code)
    except KeyError:
        raise HTTPException(404)
    return {"ok": True}


@router.post("/classrooms/{code}/assign")
def assign(code: str, body: dict, actor: Actor = Depends(get_actor)):
    try:
        classrooms.assign(actor, code, body.get("lesson_ids", []))
    except KeyError:
        raise HTTPException(404)
    return {"ok": True}


@router.delete("/classrooms/{code}/students/{sid_prefix}")
def rm_student(code: str, sid_prefix: str, actor: Actor = Depends(get_actor)):
    try:
        classrooms.remove_student(actor, code, sid_prefix)
    except KeyError:
        raise HTTPException(404)
    return {"ok": True}


@router.put("/classrooms/{code}/students/{sid_prefix}/mute")
def mute_student(code: str, sid_prefix: str, body: dict, actor: Actor = Depends(get_actor)):
    try:
        classrooms.set_muted(actor, code, sid_prefix, bool(body.get("muted", True)))
    except KeyError:
        raise HTTPException(404)
    return {"ok": True}


@router.delete("/classrooms/{code}")
def del_room(code: str, actor: Actor = Depends(get_actor)):
    try:
        classrooms.delete(actor, code)
    except KeyError:
        raise HTTPException(404)
    return {"ok": True}


@router.post("/classrooms/{code}/projects")
def submit_project(code: str, body: dict, actor: Actor = Depends(get_actor)):
    """A student submits one of their own builds (snapshot) to the class. Private to the classroom."""
    from ..services.history import store
    from ..services import editproj
    bid = str(body.get("build_id", ""))
    try:
        meta = store.get(bid)
    except KeyError:
        raise HTTPException(404, "unknown build")
    if meta.get("owner_sid") != actor.sid:
        raise HTTPException(404, "unknown build")
    editproj.ensure_exports(bid)
    try:
        return classrooms.submit_project(actor, code, store.dir(bid), body.get("title") or meta["title"])
    except KeyError:
        raise HTTPException(404)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except safety.ChatBlocked as e:
        return _blocked(e)


@router.get("/classrooms/{code}/projects")
def class_projects(code: str, actor: Actor = Depends(get_actor)):
    try:
        return {"projects": classrooms.list_projects(actor, code)}
    except KeyError:
        raise HTTPException(404)


@router.get("/classrooms/{code}/projects/{pid}/{kind}")
@router.get("/classrooms/{code}/projects/{pid}/files/{kind}")
def class_project_file(code: str, pid: str, kind: str, actor: Actor = Depends(get_actor)):
    try:
        return FileResponse(classrooms.project_file(actor, code, pid, "thumb.png" if kind == "thumb" else kind))
    except KeyError:
        raise HTTPException(404)


@router.post("/classrooms/{code}/projects/{pid}/feedback")
def give_feedback(code: str, pid: str, body: dict, actor: Actor = Depends(get_actor)):
    """Teacher text comment. No ratings/scores exist. Disallowed language is blocked."""
    try:
        return classrooms.add_feedback(actor, code, pid, body.get("comment", ""))
    except KeyError:
        raise HTTPException(404)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except safety.ChatBlocked as e:
        return _blocked(e)


@router.get("/classrooms/{code}/reports")
def class_reports(code: str, actor: Actor = Depends(get_actor)):
    """CR-11 e: the TEACHER sees reports about their own class's comments first (before the site moderator's queue)."""
    try:
        role, room = classrooms.membership(actor, code)
    except KeyError:
        raise HTTPException(404)
    if role != "teacher":
        raise HTTPException(404)
    mine = [r for r in moderation.queue() if r["item_id"].startswith(f"fb:{room['code']}:")]
    return {"reports": [{"id": r["id"], "reason": r["reason"], "created": r["created"], "preview": classrooms.feedback_preview(r["item_id"])} for r in sorted(mine, key=lambda r: r["created"])]}


@router.post("/classrooms/{code}/projects/{pid}/feedback/{fid}/report")
def report_feedback(code: str, pid: str, fid: str, request: Request, body: dict, actor: Actor = Depends(get_actor)):
    report_limit(request, actor)
    try:
        classrooms.membership(actor, code)
        return moderation.report(f"fb:{code.upper()}:{pid}:{fid}", actor.sid, body.get("reason", "other"), body.get("details", ""))
    except KeyError:
        raise HTTPException(404)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/classrooms/{code}/requests")
def send_request(code: str, body: dict, actor: Actor = Depends(get_actor)):
    """Canned requests only ('I'd like to talk next class'). Any free-text field is ignored."""
    try:
        return classrooms.send_request(actor, code, body.get("kind", ""), body.get("to", ""))
    except KeyError:
        raise HTTPException(404)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/classrooms/{code}/live")
def live_view(code: str, actor: Actor = Depends(get_actor)):
    """Teacher Live view: view-only roster, owner of the class only (404 for everyone else)."""
    try:
        return classrooms.live_roster(actor, code)
    except KeyError:
        raise HTTPException(404)


@router.post("/classrooms/{code}/students/{sid}/helped")
def hand_helped(code: str, sid: str, actor: Actor = Depends(get_actor)):
    try:
        classrooms.helped(actor, code, sid)
    except KeyError:
        raise HTTPException(404)
    return {"ok": True}


@router.post("/classrooms/{code}/hand/down")
def hand_down(code: str, actor: Actor = Depends(get_actor)):
    """Student only: lower my own raised hand."""
    try:
        classrooms.lower_hand(actor, code)
    except KeyError:
        raise HTTPException(404)
    return {"hand_up": False}


@router.get("/classrooms/{code}/notifications")
def notifications(code: str, actor: Actor = Depends(get_actor)):
    try:
        return {"notifications": classrooms.notifications(actor, code)}
    except KeyError:
        raise HTTPException(404)


@router.post("/classrooms/{code}/notifications/read")
def read_notifications(code: str, actor: Actor = Depends(get_actor)):
    try:
        classrooms.mark_read(actor, code)
    except KeyError:
        raise HTTPException(404)
    return {"ok": True}


# ---- public, shareable server-rendered pages (no login, no tracking) ----
def _page(title, body, desc=""):
    p = branding.PRODUCT_NAME
    return HTMLResponse(f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>{escape(title)} · {escape(p)}</title>
<meta property="og:title" content="{escape(title)}"><meta property="og:description" content="{escape(desc)}">
<link rel=icon href=/static/favicon.png><link rel=stylesheet href=/static/style.css></head>
<body><header class=topbar><a href=/ class=brand><img src=/static/logo-header.png alt="{escape(p)}" class=logoimg></a></header>
<main class=sharepage>{body}</main></body></html>""")


@pages.get("/l/{lid}", response_class=HTMLResponse)
def lesson_page(lid: str):
    l = next((x for x in education.LESSONS if x["id"] == lid), None)
    if not l:
        raise HTTPException(404)
    steps = "".join(f"<li><b>{escape(s['title'])}</b><p>{escape(s['body'])}</p></li>" for s in l["steps"])
    body = (f"<h1>{l['emoji']} {escape(l['title'])}</h1><p class=help>{escape(branding.SECTIONS['learn'])} · "
            f"{l['minutes']} min · ages {escape(l['age'])}</p><p>{escape(l['summary'])}</p>"
            f"<h3>Objective</h3><p>{escape(l['objective'])}</p><ol class=steps>{steps}</ol>"
            f"<h3>Teacher notes</h3><p>{escape(l['teacher_notes'])}</p>"
            f"<p><a class='btn primary' href='/#learn/{lid}'>Open this lesson in {escape(branding.PRODUCT_NAME)}</a></p>")
    return _page(l["title"], body, l["summary"])


@pages.get("/p/{pid}", response_class=HTMLResponse)
def project_page(pid: str, actor: Actor = Depends(get_actor)):
    guards.showcase_gate(actor)
    try:
        i = catalog.get(pid, actor)
    except catalog.Denied:
        raise HTTPException(404)
    i = catalog.resolve(i)
    thumb = f"<img src='/api/showcase/{pid}/thumb' class=sharethumb alt=''>" if i.get("has_thumb") else ""
    ex = "<p class=pill>EXAMPLE seed data - not a real creator project</p>" if i.get("example") else ""
    files = "".join(f"<li><a href='/api/showcase/{pid}/files/{escape(f['name'])}'>{escape(f['name'])}</a> ({f['size_kb']} KB)</li>" for f in i["files"])
    _pub = catalog.public(i, actor)
    eng = f" · {_pub['likes']} {'nozzle' if _pub['likes'] == 1 else 'nozzles'} · ⬇ {_pub['downloads']}" if _pub["likes"] is not None else ""
    cl = credits.credit_line(i)
    credit = (f"<p class=credit>Credit: <b>{escape(cl['creator'])}</b>" + (f" · Licence: {_lic(cl['licence'], cl['licence_url'])}" if cl["licence"] else "") + " · <a href='/credits'>Thank you &amp; credits</a></p>") if cl else ""
    body = (f"{ex}<h1>{escape(i['title'])}</h1><p class=help>by {escape(i['creator'])} · {escape(i['mode'])} · free{eng}</p>{credit}{thumb}"
            f"<p>{escape(i['description'])}</p><p>{' '.join('<span class=pill>' + escape(t) + '</span>' for t in i['tags'])}</p>"
            f"<h3>Free downloads</h3>{('<ul>' + files + '</ul>') if files else '<p class=help>No model yet.</p>'}")
    return _page(i["title"], body, i["description"])


@pages.get("/u/{uid}", response_class=HTMLResponse)
def user_page(uid: str, actor: Actor = Depends(get_actor)):
    guards.showcase_gate(actor)
    _, u = idn.user_by_id(uid)
    if not u and uid not in catalog.CREATORS:
        raise HTTPException(404)
    if u and not privacy.can_view_profile(actor, uid):
        raise HTTPException(404)
    name = u["display_name"] if u else catalog.CREATORS[uid]
    teen = bool(u) and idn.age_of(u) < 18
    lk = "" if (teen or not u) else "".join(
        f"<li>{escape(v['handle'])} on <a rel='nofollow noopener noreferrer' target=_blank href='{escape(v['url'])}'>{escape(k)}</a> "
        f"<span class=pill>{'verified' if v.get('verified') else 'unverified'}</span></li>" for k, v in u.get("links", {}).items())
    projs = "".join(f"<li><a href='/p/{i['id']}'>{escape(i['title'])}</a></li>" for i in catalog.list_items(actor, "free") if i["creator_id"] == uid)
    body = (f"<h1>{escape(name)}</h1><h3>Projects</h3><ul>{projs or '<li>None yet</li>'}</ul>"
            f"{'<h3>Also find me on</h3><ul>' + lk + '</ul>' if lk else ''}")
    return _page(name, body)


@pages.get("/admin/moderation", response_class=HTMLResponse)
def moderation_page():
    """The page itself holds no data: it asks for the admin token and then calls the token-protected API."""
    return FileResponse(STATIC_DIR / "moderation.html", headers={"X-Robots-Tag": "noindex, nofollow", "Cache-Control": "no-store"})


def _lic(name, url):
    if not name:
        return ""
    return f"<a href='{escape(url)}' rel='noopener noreferrer' target=_blank>{escape(name)}</a>" if str(url).startswith("https://") else escape(name)


@pages.get("/credits", response_class=HTMLResponse)
def credits_page():
    """Thank you / Credits. Every word comes from app/credits.json; versions and licences are read from what is installed."""
    d = credits.data()
    t = d["tools"]

    def rows(items):
        return "".join(
            f"<tr><td>{('<a href=\'' + escape(i['url']) + '\' rel=\'noopener noreferrer\' target=_blank>' + escape(i['name']) + '</a>') if i.get('url', '').startswith('https://') else escape(i['name'])}</td>"
            f"<td>{escape(i.get('version') or '')}</td><td>{escape(i['licence'])}</td><td>{escape(i['what'])}</td></tr>" for i in items)

    def table(items):
        return ("<div class=tablewrap><table class=credits><thead><tr><th scope=col>Name</th><th scope=col>Version</th><th scope=col>Licence</th><th scope=col>What it does for ZEIM</th></tr></thead>"
                f"<tbody>{rows(items)}</tbody></table></div>")

    def people(sec):
        ps = sec.get("people") or []
        return ("<ul>" + "".join(f"<li>{escape(x)}</li>" for x in ps) + "</ul>") if ps else f"<p class=help>{escape(sec['empty'])}</p>"

    mk = credits.makers()
    mk_html = ("".join(
        f"<details class=maker><summary><b>{escape(m['creator'])}</b> <span class=help>({len(m['models'])} model{'s' if len(m['models']) != 1 else ''})</span></summary><ul>"
        + "".join(f"<li>{escape(x['title'])} · {_lic(x['licence'], x['licence_url'])}</li>" for x in m["models"]) + "</ul></details>" for m in mk)
        if mk else f"<p class=help>{escape(d['creators']['empty'])}</p>")
    tk = d["takedown"]
    contact = " " + escape(("Contact: " + tk["contact"]) if tk.get("contact") else tk.get("contact_placeholder", ""))
    body = (f"<h1>{escape(d['title'])}</h1><p>{escape(d['intro'])}</p>"
            f"<h2>{escape(t['heading'])}</h2><p class=help>{escape(t['blurb'])}</p>{table(credits.python_packages())}"
            f"<h3>{escape(t['system_heading'])}</h3>{table(credits.system_tools())}"
            f"<h3>{escape(t['bundled_heading'])}</h3>{table(credits.bundled())}<p class=help>{escape(t['others'])}</p>"
            f"<h2>{escape(d['creators']['heading'])}</h2><p class=help>{escape(d['creators']['blurb'])}</p>{mk_html}<p class=help>{escape(d['creators']['originals_note'])}</p>"
            f"<h2>{escape(d['testers']['heading'])}</h2><p class=help>{escape(d['testers']['blurb'])}</p>{people(d['testers'])}"
            f"<h2>{escape(d['teachers']['heading'])}</h2><p class=help>{escape(d['teachers']['blurb'])}</p>{people(d['teachers'])}"
            f"<h2>{escape(d['trademarks']['heading'])}</h2><p>{escape(d['trademarks']['text'])}</p>"
            f"<h2>{escape(tk['heading'])}</h2><p>{escape(tk['text'])}{contact}</p>"
            "<p class=help><a href='/static/COMMUNITY_GUIDELINES.html'>Rules</a> · <a href='/static/privacy.html'>Privacy</a> · <a href='/static/terms.html'>Terms</a></p>"
            f"<p><a class='btn primary' href='/'>Back to {escape(branding.PRODUCT_NAME)}</a></p>")
    return _page("Thank you", body, "The people and projects behind ZEIM.")
