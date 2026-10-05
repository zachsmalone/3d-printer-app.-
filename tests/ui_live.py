"""Teacher Live view in a real browser (view-only roster): real table, no photos, hand raised -> polite announcement + 'Needs help' text, Helped clears,
stable order, optional sort, polling stops on close, student notice.  390px, Chrome + WebKit (axe in Chrome).   python tests/ui_live.py URL"""
import json, os, sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1]
AXE = os.environ.get("AXE_JS") or "/workspace/a11y-tools/node_modules/axe-core/axe.min.js"
bad = []
def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c: bad.append(n)
def axe(pg, label):
    if not os.path.exists(AXE): return
    pg.add_script_tag(path=AXE)
    r = pg.evaluate("axe.run(document.querySelector('#dlgLive'), {runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','best-practice']}}).then(r=>r.violations.map(v=>({id:v.id,n:v.nodes.length,t:v.nodes.slice(0,3).map(n=>n.target.join(' '))})))")
    ok(f"axe: {label}", not r, json.dumps(r)[:600])

def run(name, launch, with_axe):
    try: b = launch()
    except Exception as e: print(f"SKIP {name}: {str(e).splitlines()[0][:80]}"); return
    errs = []; tag = name[:2]
    tc = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True, bypass_csp=True)
    tc.request.post(URL + "/api/me/signup", data={"display_name": "Ms T", "dob": "1980-01-01"})
    code = tc.request.post(URL + "/api/classrooms", data={"name": f"Room {tag}", "password": "bluebird-77"}).json()["code"]
    studs = {}
    for n in ("Ant", "Bee", "Cat"):
        sc = b.new_context(bypass_csp=True); sc.request.post(URL + "/api/classrooms/join", data={"code": code, "nickname": n, "password": "bluebird-77"}); studs[n] = sc
    lid = studs["Ant"].request.get(URL + "/api/learn/lessons").json()["lessons"][0]["id"]
    studs["Ant"].request.post(URL + f"/api/learn/lessons/{lid}/steps/0", data={"done": True})
    pg = tc.new_page(); pg.on("pageerror", lambda e: errs.append(str(e))); pg.goto(URL); pg.wait_for_timeout(800)
    pg.click("#mainNav [data-view=learn]"); pg.click("#btnTeacher"); pg.wait_for_selector("[data-live]")
    pg.click("[data-live]"); pg.wait_for_selector("#dlgLive[open]"); pg.wait_for_selector("#liveRows tr")
    ok(f"{name}: a real table with named column headers", pg.locator("#dlgLive table.live th[scope=col]").count() == 5 and pg.locator("#dlgLive caption").count() == 1)
    names = pg.locator("#liveRows th[scope=row]").all_inner_texts()
    ok(f"{name}: one row per student, join order", names == ["Ant", "Bee", "Cat"], names)
    ok(f"{name}: lesson and steps shown as 'N of M steps' for the student who ticked one", "1 of" in pg.locator("#liveRows tr:first-child .c-l").inner_text())
    ok(f"{name}: view only: no pictures, no edit controls in the roster", pg.locator("#dlgLive img, #dlgLive canvas, #dlgLive input[type=text], #dlgLive textarea").count() == 0 and "View only" in pg.inner_text("#liveNote"))
    ok(f"{name}: no sideways scroll", pg.evaluate("document.documentElement.scrollWidth") <= 390)
    if with_axe: axe(pg, "live view dialog")
    studs["Cat"].request.post(URL + f"/api/classrooms/{code}/requests", data={"kind": "need_help"})
    pg.wait_for_selector("#liveRows tr.hand", timeout=20000)
    ok(f"{name}: raised hand is text + icon, announced politely, row order unchanged",
       "Needs help" in pg.inner_text("#liveRows tr.hand") and "Cat needs help." in pg.inner_text("#liveSay") and pg.locator("#liveRows th[scope=row]").all_inner_texts() == ["Ant", "Bee", "Cat"] and pg.get_attribute("#liveSay", "aria-live") == "polite")
    hb = pg.locator("#liveRows [data-helped]"); ok(f"{name}: Helped button is at least 44px", hb.bounding_box()["height"] >= 43.5, hb.bounding_box())
    pg.check("#liveSort"); pg.wait_for_timeout(200)
    ok(f"{name}: the optional sort puts the hand first", pg.locator("#liveRows th[scope=row]").all_inner_texts()[0] == "Cat")
    pg.uncheck("#liveSort"); pg.wait_for_timeout(200)
    hb.click(); pg.wait_for_timeout(800)
    ok(f"{name}: Helped clears the hand", pg.locator("#liveRows tr.hand").count() == 0 and "Marked as helped" in pg.inner_text("#liveSay"))
    ok(f"{name}: polling is on while open", pg.evaluate("window.__liveTimer() !== null"))
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
    ok(f"{name}: closing the window stops the refresh", pg.evaluate("window.__liveTimer() === null"))
    # a student can't open it; a student sees the notice
    r = studs["Ant"].request.get(URL + f"/api/classrooms/{code}/live"); ok(f"{name}: a student gets 404 from the roster", r.status == 404)
    sp = studs["Bee"].new_page(); sp.goto(URL); sp.wait_for_timeout(600); sp.click("#mainNav [data-view=learn]"); sp.wait_for_selector("#classNotice")
    ok(f"{name}: the student sees what the teacher can see", "cannot see your photos" in sp.inner_text("#classNotice") and "nickname" in sp.inner_text("#classNotice"))
    ok(f"{name}: no page errors", not errs, errs)
    for c in studs.values(): c.close()
    tc.close(); b.close()

with sync_playwright() as p:
    run("chrome", lambda: p.chromium.launch(channel="chrome"), True)
    run("webkit", lambda: p.webkit.launch(), False)
sys.exit(1 if bad else 0)
