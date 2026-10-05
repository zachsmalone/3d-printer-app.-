"""The two last native prompt() boxes are gone: a student sends a build to the class through a dialog with a list; a teacher writes feedback in a dialog
that keeps what was typed when it is refused. Chrome + WebKit, 390px.   python tests/ui_prompts.py URL   (TEMP-data server, not 8765)"""
import os, sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1]
SAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample.png")
bad = []
def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, x)
    if not c: bad.append(n)

def run(name, launch):
    try: b = launch()
    except Exception as e: print(f"SKIP {name}: {str(e).splitlines()[0][:80]}"); return
    errs = []; dialogs = []
    def ctx_page():
        c = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        pg = c.new_page(); pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: (dialogs.append(d.type), d.dismiss()))
        return c, pg
    tc, tp = ctx_page(); tp.goto(URL); tp.wait_for_timeout(500)
    assert tc.request.post(URL + "/api/me/signup", data={"display_name": "Ms T", "dob": "1980-01-01"}).ok
    room = tc.request.post(URL + "/api/classrooms", data={"name": "Period 1", "password": "pass-1234"}).json(); code = room["code"]
    sc, sp = ctx_page(); sp.goto(URL); sp.wait_for_timeout(500)
    assert sc.request.post(URL + "/api/classrooms/join", data={"code": code, "nickname": "Robo9", "password": "pass-1234"}).ok
    g = sc.request.post(URL + "/api/generate", multipart={"mode": "relief", "width_mm": "50", "resolution": "40", "photo_ack": "true",
                        "file": {"name": "s.png", "mimeType": "image/png", "buffer": open(SAMPLE, "rb").read()}}); assert g.ok, g.text()
    sp.reload(); sp.wait_for_timeout(800)
    sp.click('#mainNav [data-view=learn]'); sp.wait_for_selector("#clsSubmit", timeout=10000)
    sp.click("#clsSubmit"); sp.wait_for_selector("#dlgPickBuild[open]", timeout=5000)
    ok(f"{name}: 'send a build' is a dialog with a list (no prompt box)", sp.locator("#pbList input[type=radio]").count() >= 1 and not dialogs)
    sp.click("#pbSend"); sp.wait_for_selector(".toast.ok", timeout=8000)
    ok(f"{name}: sending works and the dialog closes", not sp.is_visible("#dlgPickBuild") and "Submitted" in sp.inner_text(".toast.ok"))
    tp.reload(); tp.wait_for_timeout(800); tp.click("#mainNav [data-view=learn]"); tp.click("#btnTeacher"); tp.wait_for_selector("[data-fb]", timeout=10000)
    tp.click("[data-fb]"); tp.wait_for_selector("#dlgFeedback[open]", timeout=5000)
    ok(f"{name}: feedback is a dialog (no prompt box)", not dialogs)
    tp.click("#fbSave"); tp.wait_for_selector("#dlgFeedback .inline-msg", timeout=4000)
    ok(f"{name}: empty feedback is refused inline", "write" in tp.inner_text("#dlgFeedback .inline-msg").lower())
    tp.fill("#fbText", "Call me at 555-123-4567"); tp.click("#fbSave"); tp.wait_for_timeout(1500)
    ok(f"{name}: a refused comment stays inline and keeps the typed text", tp.input_value("#fbText") == "Call me at 555-123-4567" and tp.locator("#dlgFeedback .inline-msg").count() == 1 and tp.is_visible("#dlgFeedback"), tp.inner_text("#dlgFeedback .inline-msg"))
    tp.fill("#fbText", "Nice smooth layers!"); tp.click("#fbSave"); tp.wait_for_selector(".toast.ok:has-text('Feedback saved')", timeout=8000)
    ok(f"{name}: good feedback is saved and the dialog closes", not tp.is_visible("#dlgFeedback"))
    ok(f"{name}: no native dialog ever opened", not dialogs, dialogs)
    ok(f"{name}: no page errors", not errs, errs)
    tc.close(); sc.close(); b.close()

with sync_playwright() as p:
    run("chrome", lambda: p.chromium.launch(channel="chrome"))
    run("webkit", lambda: p.webkit.launch())
sys.exit(1 if bad else 0)
