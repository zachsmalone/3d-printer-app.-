"""Mode dropdown (Beginner / Experienced): labels, live announcements, no Teacher mode (removed 2026-10-12), old saved values fall back.  Chrome + WebKit, 390px.   python tests/ui_mode.py URL  (TEMP-data server)"""
import re, sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1]
bad = []
def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, x if not c else "")
    if not c: bad.append(n)

def run(name, launch):
    try: b = launch()
    except Exception as e: print(f"SKIP {name}: {str(e).splitlines()[0][:80]}"); return
    errs = []
    def page(storage=None):
        ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e))); pg.goto(URL.rstrip("/") + "/#studio"); pg.wait_for_timeout(700); return ctx, pg
    ctx, pg = page()
    ok(f"{name}: a labelled Mode select with two plain-word options",
       pg.inner_text("label[for=modeSel]") == "Mode" and pg.eval_on_selector_all("#modeSel option", "o=>o.map(x=>x.textContent)") == ["Beginner", "Experienced"])
    ok(f"{name}: Beginner is the default", pg.input_value("#modeSel") == "beginner" and pg.evaluate("document.body.dataset.level") == "beginner")
    bx = pg.locator("#modeSel").bounding_box(); fs = pg.evaluate("parseFloat(getComputedStyle(document.querySelector('#modeSel')).fontSize)")
    ok(f"{name}: the select is at least 44px tall and 16px type (no iOS zoom)", bx["height"] >= 44 and fs >= 16, (bx, fs))
    ok(f"{name}: the word Expert is not shown to people", not re.search(r"\bExpert\b", pg.inner_text("body")))
    pg.select_option("#modeSel", "expert"); pg.wait_for_timeout(300)
    ok(f"{name}: Experienced shows the settings and announces itself politely",
       pg.is_visible("#expertOpts") and not pg.is_visible("#beginnerOpts") and "Experienced mode on" in pg.inner_text("#modeStatus")
       and pg.get_attribute("#modeStatus", "aria-live") == "polite")
    ok(f"{name}: there is no Teacher mode, teacher note or classroom bar (school features removed 2026-10-12)",
       not pg.locator("#teacherNote").count() and not pg.locator("#classBar").count() and not pg.locator("#btnTeacher").count())
    pg.evaluate("localStorage.level='teacher'"); pg.reload(); pg.wait_for_timeout(800)
    ok(f"{name}: an old saved Teacher choice quietly becomes Beginner", pg.input_value("#modeSel") == "beginner")
    pg.evaluate("localStorage.level='nonsense'"); pg.reload(); pg.wait_for_timeout(600)
    ok(f"{name}: a bad saved value is ignored", pg.input_value("#modeSel") == "beginner")
    ok(f"{name}: no page errors", not errs, errs)
    ctx.close(); b.close()

with sync_playwright() as p:
    run("chrome", lambda: p.chromium.launch(channel="chrome"))
    run("webkit", lambda: p.webkit.launch())
sys.exit(1 if bad else 0)
