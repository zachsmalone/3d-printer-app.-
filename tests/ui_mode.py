"""Mode dropdown (Beginner / Experienced / Teacher): labels, live announcements, Teacher gated to adult accounts with a non-modal explainer,
classroom bar, restore on reload, quiet fallback after sign-out.  Chrome + WebKit, 390px.   python tests/ui_mode.py URL  (TEMP-data server)"""
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
        pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e))); pg.goto(URL); pg.wait_for_timeout(700); return ctx, pg
    ctx, pg = page()
    ok(f"{name}: a labelled Mode select with three plain-word options",
       pg.inner_text("label[for=modeSel]") == "Mode" and pg.eval_on_selector_all("#modeSel option", "o=>o.map(x=>x.textContent)") == ["Beginner", "Experienced", "Teacher"])
    ok(f"{name}: Beginner is the default", pg.input_value("#modeSel") == "beginner" and pg.evaluate("document.body.dataset.level") == "beginner")
    bx = pg.locator("#modeSel").bounding_box(); fs = pg.evaluate("parseFloat(getComputedStyle(document.querySelector('#modeSel')).fontSize)")
    ok(f"{name}: the select is at least 44px tall and 16px type (no iOS zoom)", bx["height"] >= 44 and fs >= 16, (bx, fs))
    ok(f"{name}: the word Expert is not shown to people", not re.search(r"\bExpert\b", pg.inner_text("body")))
    pg.select_option("#modeSel", "expert"); pg.wait_for_timeout(300)
    ok(f"{name}: Experienced shows the settings and announces itself politely",
       pg.is_visible("#expertOpts") and not pg.is_visible("#beginnerOpts") and "Experienced mode on" in pg.inner_text("#modeStatus")
       and pg.get_attribute("#modeStatus", "aria-live") == "polite")
    pg.focus("#modeSel"); pg.select_option("#modeSel", "teacher"); pg.wait_for_timeout(300)
    ok(f"{name}: a visitor choosing Teacher stays where they were, with a non-modal explainer", pg.input_value("#modeSel") == "expert"
       and pg.is_visible("#teacherNote") and "grown-up account" in pg.inner_text("#teacherNote") and not pg.is_visible("#classBar")
       and pg.evaluate("!document.querySelector('dialog[open]')"))
    ok(f"{name}: focus stays on the select", pg.evaluate("document.activeElement.id") == "modeSel")
    ok(f"{name}: the status line says which mode you are still in", "still in Experienced mode" in pg.inner_text("#modeStatus"))
    # explainer button -> account dialog -> sign up as an adult -> lands in Teacher mode
    pg.click("#tnActions >> text=Make a free adult account"); pg.wait_for_selector("#dlgAccount[open]")
    pg.fill("#su_name", "Ms Test"); pg.fill("#su_user", f"MsTest_{name[:2]}"); pg.fill("#su_dob", "1980-02-02"); pg.click("#su_go")
    pg.wait_for_selector("body[data-level=teacher]", timeout=8000); pg.wait_for_timeout(300)
    ok(f"{name}: after the adult account exists, Teacher mode turns on", pg.input_value("#modeSel") == "teacher" and "Teacher mode on" in pg.inner_text("#modeStatus"))
    pg.evaluate("document.querySelector('#dlgAccount').close()")
    ok(f"{name}: Teacher is the Beginner view plus the classroom bar", pg.is_visible("#classBar") and pg.is_visible("#beginnerOpts") and not pg.is_visible("#expertOpts"))
    ok(f"{name}: with no class yet the bar says so and offers Teacher tools", "No class yet" in pg.inner_text("#classBar") and pg.is_visible("#btnTeacherTools"))
    pg.evaluate("fetch('/api/classrooms',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({name:'Room 12',password:'bluebird77'})})"); pg.wait_for_timeout(500)
    pg.reload(); pg.wait_for_timeout(1200)
    ok(f"{name}: Teacher is restored on reload for the adult account, with the class name, join code and send state in the bar",
       pg.input_value("#modeSel") == "teacher" and "Room 12" in pg.inner_text("#classBar") and re.search(r"Join code\s*[A-Z0-9]{6}", pg.inner_text("#classBar"))
       and "Off" in pg.inner_text("#classBar"), pg.inner_text("#classBar"))
    pg.click("#btnTeacherTools"); pg.wait_for_selector("#dlgTeacher[open]"); ok(f"{name}: Teacher tools opens", True); pg.evaluate("document.querySelector('#dlgTeacher').close()")
    ok(f"{name}: no horizontal scroll in Teacher mode", pg.evaluate("document.documentElement.scrollWidth") <= 390)
    # sign-out (cookie gone) -> quiet fall back to Beginner
    ctx.clear_cookies(); pg.reload(); pg.wait_for_timeout(1200)
    ok(f"{name}: without the adult account, a saved Teacher choice falls back to Beginner", pg.input_value("#modeSel") == "beginner" and not pg.is_visible("#classBar"))
    pg.evaluate("localStorage.level='nonsense'"); pg.reload(); pg.wait_for_timeout(600)
    ok(f"{name}: a bad saved value is ignored", pg.input_value("#modeSel") == "beginner")
    ctx.close()
    # teen: refused, different words
    ctx, pg = page()
    pg.click("#btnAccount"); pg.fill("#su_name", "Tess"); pg.fill("#su_dob", "2011-01-01"); pg.click("#su_go"); pg.wait_for_selector("#un_now", timeout=8000)
    pg.evaluate("document.querySelector('#dlgAccount').close()")
    pg.select_option("#modeSel", "teacher"); pg.wait_for_timeout(300)
    ok(f"{name}: a teen is told Teacher mode is for adults", pg.input_value("#modeSel") == "beginner" and "for adults" in pg.inner_text("#teacherNote") and not pg.is_visible("#classBar"))
    ok(f"{name}: the teen explainer closes with its button and focus returns to the select",
       (pg.click("#tnActions >> text=Close"), pg.evaluate("document.activeElement.id") == "modeSel" and not pg.is_visible("#teacherNote"))[1])
    ok(f"{name}: no page errors", not errs, errs)
    ctx.close(); b.close()

with sync_playwright() as p:
    run("chrome", lambda: p.chromium.launch(channel="chrome"))
    run("webkit", lambda: p.webkit.launch())
sys.exit(1 if bad else 0)
