"""Edge 1: refusals appear INLINE in the dialog, stay put, and keep what was typed (no toast).  Chrome + WebKit, 390px.
python tests/ui_inline.py URL"""
import sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1]
bad = []
def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, x)
    if not c: bad.append(n)

def run(name, launch):
    try: b = launch()
    except Exception as e: print(f"SKIP {name}: {str(e).splitlines()[0][:80]}"); return
    errs = []
    ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
    pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL); pg.wait_for_timeout(700)
    # --- under-13 sign-up: calm panel with a Join-a-class button, not a toast over an unchanged form
    pg.click("#btnAccount"); pg.fill("#su_name", "Kiddo"); pg.fill("#su_dob", "2018-03-04"); pg.click("#su_go")
    pg.wait_for_selector("#accBody .calm", timeout=8000)
    ok(f"{name}: under-13 refusal is a panel in the dialog", pg.is_visible("#suJoin") and not pg.is_visible("#su_go") and "can't create an account" in pg.inner_text("#accBody"))
    pg.wait_for_timeout(9000)
    ok(f"{name}: ...and it is still there after the toast time", pg.is_visible("#accBody .calm") and pg.locator(".toast").count() == 0)
    pg.click("#suJoin"); pg.wait_for_selector("#dlgJoin[open]", timeout=4000)
    # --- join: wrong password stays inline and keeps the typed text
    pg.fill("#j_code", "ZZZZZZ"); pg.fill("#j_pw", "not-the-password"); pg.fill("#j_nick", "Robo9"); pg.click("#btnDoJoin")
    pg.wait_for_selector("#dlgJoin .inline-msg", timeout=8000); msg1 = pg.inner_text("#dlgJoin .inline-msg")
    pg.wait_for_timeout(9000)
    ok(f"{name}: wrong class password message is inline, persistent, role=alert", pg.is_visible("#dlgJoin .inline-msg") and pg.get_attribute("#dlgJoin .inline-msg", "role") == "alert", msg1)
    ok(f"{name}: ...and the typed code, password and nickname are kept", pg.input_value("#j_code") == "ZZZZZZ" and pg.input_value("#j_pw") == "not-the-password" and pg.input_value("#j_nick") == "Robo9")
    pg.fill("#j_nick", "fuck123"); pg.click("#btnDoJoin"); pg.wait_for_timeout(1500)
    ok(f"{name}: a blocked nickname is refused inline too (one message, replaced not stacked)", pg.locator("#dlgJoin .inline-msg").count() == 1 and pg.input_value("#j_nick") == "fuck123", pg.inner_text("#dlgJoin .inline-msg"))
    ok(f"{name}: no toast carries the refusal", pg.locator(".toast.err").count() == 0)
    ok(f"{name}: no page errors", not errs, errs)
    ctx.close(); b.close()

with sync_playwright() as p:
    run("chrome", lambda: p.chromium.launch(channel="chrome"))
    run("webkit", lambda: p.webkit.launch())
sys.exit(1 if bad else 0)
