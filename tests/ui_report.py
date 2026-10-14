"""Edge 4: Report is a proper dialog with choices (no prompt(), no typed code words); examples offer no Report/Follow.  390px, Chrome + WebKit.
python tests/ui_report.py URL"""
import os, sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PNG = open(os.path.join(ROOT, "static", "sample.png"), "rb").read()
bad = []
def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, x)
    if not c: bad.append(n)

def run(name, launch):
    try: b = launch()
    except Exception as e: print(f"SKIP {name}: {str(e).splitlines()[0][:80]}"); return
    # an adult publishes one public project through the API
    owner = b.new_context(); r = owner.request
    r.post(URL + "/api/me/signup", data={"display_name": "Ada", "dob": "1985-05-05"})
    g = r.post(URL + "/api/generate", multipart={"file": {"name": "a.png", "mimeType": "image/png", "buffer": PNG}, "mode": "relief", "photo_ack": "true"}).json()
    item = r.post(URL + "/api/showcase", data={"build_id": g["id"], "title": "Desk fox", "description": "", "tags": [], "accept_guidelines": True, "nsfw": False, "visibility": "public"}).json()
    errs = []; dialogs = []
    ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
    pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: (dialogs.append(d.type), d.dismiss()))
    pg.goto(URL.rstrip("/") + "/#studio"); pg.wait_for_timeout(700); pg.click("#mainNav [data-view=showcase]"); pg.wait_for_selector("#shGrid .pcard", timeout=15000)
    pg.click("#shGrid .pcard:has-text('Retro Comic') >> nth=0") if pg.locator("#shGrid .pcard:has-text('Retro Comic')").count() else pg.click("#shGrid .pcard >> nth=0")
    pg.wait_for_selector("#dlgItem[open]")
    if pg.locator("#dlgItem .pill:has-text('EXAMPLE')").count():
        ok(f"{name}: an EXAMPLE item offers no Report and no Follow", pg.locator("#itReport").count() == 0 and pg.locator("#itFollow").count() == 0)
    pg.click("#dlgItem [data-close]"); pg.wait_for_timeout(300)
    pg.click("#shClear") if pg.is_visible("#shClear") else None
    pg.fill("#shSearch", "Desk fox"); pg.press("#shSearch", "Enter"); pg.wait_for_selector("#shGrid .pcard:has-text('Desk fox')", timeout=10000)
    pg.click("#shGrid .pcard:has-text('Desk fox')"); pg.wait_for_selector("#itReport", timeout=8000)
    box = pg.locator("#itReport").bounding_box(); ok(f"{name}: Report button is >= 44px", box["height"] >= 44, box)
    pg.click("#itReport"); pg.wait_for_selector("#dlgReport[open]")
    ok(f"{name}: dialog shows eight plain-language choices and no code words", pg.locator("#dlgReport [name=repReason]").count() == 8 and "minor_safety" not in pg.inner_text("#dlgReport"))
    small = pg.locator("#dlgReport label.choice").evaluate_all("els => els.map(e => e.getBoundingClientRect().height).filter(h => h < 44)")
    ok(f"{name}: every choice is a >= 44px target", not small, small)
    ok(f"{name}: dialog fits 390px", pg.evaluate("(() => { const d = document.querySelector('#dlgReport .dlg'); return d.scrollWidth <= d.clientWidth + 1 && d.getBoundingClientRect().width <= 390; })()"))
    pg.click("#repSend"); pg.wait_for_selector("#dlgReport .inline-msg")
    ok(f"{name}: sending with no choice says so inline, dialog stays open", pg.is_visible("#dlgReport .inline-msg") and pg.locator("#dlgReport[open]").count() == 1)
    pg.click("#dlgReport label.choice:has-text('Mean or unkind')"); pg.fill("#repDetails", "rude title"); pg.click("#repSend"); pg.wait_for_timeout(1500)
    ok(f"{name}: a report is sent and the dialog closes with a thank-you", pg.locator("#dlgReport[open]").count() == 0 and "Thank you" in pg.inner_text("#toasts"))
    ok(f"{name}: no native prompt/confirm appeared", not dialogs, dialogs)
    ok(f"{name}: no page errors", not errs, errs)
    ctx.close(); owner.close(); b.close()

with sync_playwright() as p:
    run("chrome", lambda: p.chromium.launch(channel="chrome"))
    run("webkit", lambda: p.webkit.launch())
sys.exit(1 if bad else 0)
