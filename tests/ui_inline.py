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
    pg.goto(URL.rstrip("/") + "/#studio"); pg.wait_for_timeout(700)
    # --- under-13 sign-up: calm panel (no class-code path any more), not a toast over an unchanged form
    pg.evaluate("location.hash='account'"); pg.click("#btnAccount"); pg.fill("#su_name", "Kiddo"); pg.fill("#su_dob", "2018-03-04"); pg.click("#su_go")
    pg.wait_for_selector("#accBody .calm", timeout=8000)
    ok(f"{name}: under-13 refusal is a panel in the dialog", pg.locator("#suJoin").count() == 0 and not pg.is_visible("#su_go") and "can't create an account" in pg.inner_text("#accBody"))
    pg.wait_for_timeout(9000)
    ok(f"{name}: ...and it is still there after the toast time", pg.is_visible("#accBody .calm") and pg.locator(".toast").count() == 0)
    ok(f"{name}: no toast carries the refusal", pg.locator(".toast.err").count() == 0)
    ok(f"{name}: no page errors", not errs, errs)
    ctx.close(); b.close()

with sync_playwright() as p:
    run("chrome", lambda: p.chromium.launch(channel="chrome"))
    run("webkit", lambda: p.webkit.launch())
sys.exit(1 if bad else 0)
