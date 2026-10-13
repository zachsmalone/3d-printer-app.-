"""Learning library (Spark Lab) + public shareable pages. No grades, scores or school records (2026-10-12)."""
from __future__ import annotations

from html import escape

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from .. import branding
from ..config import STATIC as STATIC_DIR
from ..community import catalog, education, privacy
from ..services import credits
from . import guards
from ..community import identity as idn
from ..community.identity import Actor, get_actor

router = APIRouter(prefix="/api")
pages = APIRouter()


@router.get("/learn/lessons")
def lessons(actor: Actor = Depends(get_actor)):
    return {"lessons": education.catalog(actor.sid),
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


@router.delete("/learn/progress")
def reset_progress(actor: Actor = Depends(get_actor)):
    education.reset(actor.sid)
    return {"ok": True}


# ---- public, shareable server-rendered pages (no login, no tracking) ----
def _page(title, body, desc=""):
    p = branding.PRODUCT_NAME
    return HTMLResponse(f"""<!doctype html><html lang=en><head><meta charset=utf-8><script>try{{var t=localStorage.theme;if(t==="dark"||(!t&&matchMedia("(prefers-color-scheme: dark)").matches))document.documentElement.setAttribute("data-theme","dark")}}catch(e){{}}</script><script src="/static/theme.js" defer></script>
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
    name = (("@" + u["username"]) if u.get("username") else "a ZEIM maker") if u else catalog.CREATORS[uid]     # @username, never the display name
    lk = "" if (not u or idn.restricted(u)) else "".join(
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
            f"<h2>{escape(d['trademarks']['heading'])}</h2><p>{escape(d['trademarks']['text'])}</p>"
            f"<h2>{escape(tk['heading'])}</h2><p>{escape(tk['text'])}{contact}</p>"
            "<p class=help><a href='/static/COMMUNITY_GUIDELINES.html'>Rules</a> · <a href='/static/privacy.html'>Privacy</a> · <a href='/static/terms.html'>Terms</a></p>"
            f"<p><a class='btn primary' href='/'>Back to {escape(branding.PRODUCT_NAME)}</a></p>")
    return _page("Thank you", body, "The people and projects behind ZEIM.")
