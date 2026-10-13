"""Accessibility round 2 top-10 (reports/accessibility-round2.md, tested on 22f091b): labels, keyboard lesson cards and Edit steps,
friendly error text, 3px focus ring in Dark, skip link, stacked-dialog focus trap, 24/44px targets, Sign out explains the disabled button.
(Live view items 3-4 removed with school features, 2026-10-12.)  390px + 1280px, Chrome + WebKit (axe in Chrome).  No screen reader or real phone here."""
import json, os, sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1]; bad = []
AXE = os.environ.get("AXE_JS") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "axe.min.js")
def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c: bad.append(n)
def axe_rules(pg, root, rules):
    if not os.path.exists(AXE): raise SystemExit("FAIL axe missing: " + AXE)
    pg.add_script_tag(path=AXE)
    return pg.evaluate(f"axe.run(document.querySelector('{root}'), {{runOnly:{{type:'rule',values:{json.dumps(rules)}}}}}).then(r=>r.violations.map(v=>({{id:v.id,t:v.nodes.slice(0,3).map(n=>n.target.join(' '))}})))")
def run(name, launch, with_axe):
    try: b = launch()
    except Exception as e: print(f"SKIP {name}: {str(e).splitlines()[0][:80]}"); return
    errs = []
    ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True, bypass_csp=True)
    pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL.rstrip("/") + "/#studio"); pg.wait_for_timeout(800)
    # 7 skip link
    pg.keyboard.press("Tab")
    ok(f"{name}: first Tab stop is the skip link, visible on focus", pg.evaluate("document.activeElement.id") == "skipLink" and pg.locator("#skipLink").bounding_box()["y"] >= 0)
    pg.keyboard.press("Enter"); pg.wait_for_timeout(200)
    ok(f"{name}: the skip link moves focus to the visible main", pg.evaluate("document.activeElement.tagName") == "MAIN")
    # 5 friendly errors
    t = pg.evaluate("window.__errText({detail:[{loc:['body','width_mm'],msg:'x',type:'float_parsing'}]}, {status:422})")
    ok(f"{name}: a 422 list becomes a field message, never [object Object]", "Width" in t and "object" not in t.lower(), t)
    ok(f"{name}: an unknown 422 entry falls back to plain words", "isn't right" in pg.evaluate("window.__errText({detail:[{}]}, {status:422})"))
    # 1 labels: sign-up
    pg.evaluate("location.hash='account'"); pg.click("#btnAccount"); pg.wait_for_selector("#su_dob")
    ok(f"{name}: sign-up name and DOB have labels", pg.evaluate("[...document.querySelectorAll('#su_name,#su_dob')].every(i => i.labels.length === 1)"))
    if with_axe: v = axe_rules(pg, "#dlgAccount", ["label", "select-name"]); ok(f"{name}: axe label/select-name in Account", not v, v)
    pg.keyboard.press("Escape")
    # 6 dark focus ring
    pg.evaluate("document.documentElement.dataset.theme='dark'"); pg.evaluate("location.hash='account'"); pg.click("#btnAccount"); pg.wait_for_selector("#su_name"); pg.focus("#su_name")
    ow = pg.evaluate("getComputedStyle(document.querySelector('#su_name')).outlineWidth"); oc = pg.evaluate("getComputedStyle(document.querySelector('#su_name')).outlineColor")
    ok(f"{name}: dark input focus ring is the 3px --focus ring", ow == "3px" and oc in ("rgb(141, 184, 255)",), (ow, oc))
    pg.keyboard.press("Escape"); pg.evaluate("document.documentElement.removeAttribute('data-theme')")
    # 1 Settings slicer label
    pg.evaluate("location.hash='account'"); pg.click("#btnSettings"); pg.wait_for_selector("#dlgSettings[open]")
    ok(f"{name}: default slicer select has a label", pg.evaluate("document.querySelector('#set_slicer').labels.length") == 1)
    pg.keyboard.press("Escape")
    # 1 + 2 Edit: labelled dropdowns, history steps are buttons
    pg.click('#mainNav [data-view=slicer]'); pg.wait_for_timeout(400)
    ok(f"{name}: Edit's 3 dropdowns have labels", pg.evaluate("['editUnits','editPhotoMode','editFromBuild'].every(id => document.getElementById(id).labels.length === 1)"))
    pg.click("#editSample"); pg.wait_for_selector("#editOps button[data-goto]", timeout=60000)
    ok(f"{name}: Edit history steps are buttons and the current one is aria-current=step",
       pg.locator("#editOps li button[data-goto]").count() >= 1 and pg.locator('#editOps [aria-current="step"]').count() == 1)
    # 2 lesson cards keyboard
    pg.evaluate("location.hash='learn'"); pg.wait_for_selector("#lessonGrid a[data-open-lesson]")
    pg.focus("#lessonGrid a[data-open-lesson] >> nth=0"); pg.keyboard.press("Enter"); pg.wait_for_timeout(600)
    ok(f"{name}: a lesson opens from the keyboard", pg.locator("#lessonDetail input[data-step]").count() >= 1)
    # 9 targets: lesson checkboxes >= 24px
    cb = pg.locator("#lessonDetail input[data-step] >> nth=0").bounding_box()
    ok(f"{name}: lesson checkboxes are at least 24px", cb["width"] >= 23.5 and cb["height"] >= 23.5, cb)
    # 10 + 8 Sign out
    pg.evaluate("location.hash='account'"); pg.click("#btnAccount"); pg.fill("#su_name", "Ms A"); pg.fill("#su_user", f"MsA_{name}"); pg.fill("#su_dob", "1980-02-02"); pg.click("#su_go"); pg.wait_for_selector("#un_now", timeout=8000)
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
    pg.evaluate("location.hash='account'"); pg.click("#btnAccount"); pg.click("#so_open"); pg.wait_for_selector("#dlgSignout[open]"); pg.wait_for_timeout(200)
    ok(f"{name}: Sign out dialog starts on 'Show my recovery code'", pg.evaluate("document.activeElement.id") == "soCodeBtn")
    ok(f"{name}: Sign out is focusable, aria-disabled and says why", pg.get_attribute("#soGo", "aria-disabled") == "true" and not pg.evaluate("document.querySelector('#soGo').disabled")
       and "recovery code" in pg.inner_text("#soWhy"))
    ok(f"{name}: the Account dialog underneath is inert", pg.evaluate("document.querySelector('#dlgAccount').inert") is True)
    seen = set()
    for _ in range(8):
        pg.keyboard.press("Tab"); seen.add(pg.evaluate("document.activeElement.closest('dialog')?.id || document.activeElement.tagName"))
    ok(f"{name}: Tab stays inside the Sign out dialog", seen == {"dlgSignout"}, seen)
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
    ok(f"{name}: closing Sign out restores the Account dialog", pg.evaluate("document.querySelector('#dlgAccount').inert") is False)
    # 9 44px buttons at desktop width
    pg.set_viewport_size({"width": 1280, "height": 900}); pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
    small = pg.locator("button.btn:visible").evaluate_all("els => els.map(e => [e.id || e.textContent.trim().slice(0,20), e.getBoundingClientRect().height]).filter(x => x[1] && x[1] < 43.5)")
    ok(f"{name}: visible .btn buttons are at least 44px at 1280px", not small, small)
    ok(f"{name}: no page errors", not errs, errs)
    ctx.close(); b.close()
with sync_playwright() as p:
    run("chrome", lambda: p.chromium.launch(channel="chrome"), True)
    run("webkit", lambda: p.webkit.launch(), False)
sys.exit(1 if bad else 0)
