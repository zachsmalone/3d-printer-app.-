"""Education center + classrooms + public shareable pages."""
from __future__ import annotations

from html import escape

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from .. import branding
from ..community import catalog, classrooms, education, moderation, privacy, safety
from ..services import settings
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
    base = settings.base_url(request)
    return Response(classrooms.qr_svg(base, room["code"]), media_type="image/svg+xml")


@router.post("/classrooms/join")
def join_room(body: dict, actor: Actor = Depends(get_actor)):
    try:
        return classrooms.join(actor.sid, body.get("code", ""), body.get("nickname", ""), body.get("password", ""))
    except KeyError:
        raise HTTPException(404, "Wrong class code or password")
    except PermissionError as e:
        raise HTTPException(429, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


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


@router.post("/classrooms/{code}/projects/{pid}/feedback/{fid}/report")
def report_feedback(code: str, pid: str, fid: str, body: dict, actor: Actor = Depends(get_actor)):
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
    try:
        i = catalog.get(pid, actor)
    except catalog.Denied:
        raise HTTPException(404)
    thumb = f"<img src='/api/showcase/{pid}/thumb' class=sharethumb alt=''>" if i.get("has_thumb") else ""
    ex = "<p class=pill>EXAMPLE seed data - not a real creator project</p>" if i.get("example") else ""
    files = "".join(f"<li><a href='/api/showcase/{pid}/files/{escape(f['name'])}'>{escape(f['name'])}</a> ({f['size_kb']} KB)</li>" for f in i["files"])
    eng = f" · ♥ {catalog.public(i, actor)['likes']} · ⬇ {catalog.public(i, actor)['downloads']}" if catalog.public(i, actor)["likes"] is not None else ""
    body = (f"{ex}<h1>{escape(i['title'])}</h1><p class=help>by {escape(i['creator'])} · {escape(i['mode'])} · free{eng}</p>{thumb}"
            f"<p>{escape(i['description'])}</p><p>{' '.join('<span class=pill>' + escape(t) + '</span>' for t in i['tags'])}</p>"
            f"<h3>Free downloads</h3><ul>{files}</ul>")
    return _page(i["title"], body, i["description"])


@pages.get("/u/{uid}", response_class=HTMLResponse)
def user_page(uid: str, actor: Actor = Depends(get_actor)):
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
