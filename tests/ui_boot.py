"""Start-up regression for the phone test failure ('page loads, none of the buttons work'):
 1. a clean load in Chrome AND WebKit has NO page error / console error through every tab and a sample build;
 2. if a script is broken (throws, or 404) the page says so out loud (#bootError with a Reload button) instead of silently dead buttons.
python tests/ui_boot.py URL"""
import sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1]
R = []
def ok(n, c, x=""): R.append(bool(c)); print(("PASS " if c else "FAIL ") + n, x)

def run(name, launch):
    try:
        b = launch()
    except Exception as e:
        print(f"SKIP {name}: cannot launch ({str(e).splitlines()[0][:80]})"); return
    def page(route=None):
        ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=name == "chrome")
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append("pageerror: " + str(e)))
        pg.on("console", lambda m: errs.append("console.error: " + m.text) if m.type == "error" else None)
        if route: route(ctx)
        return ctx, pg, errs
    # 1. clean run
    ctx, pg, errs = page()
    pg.goto(URL.rstrip("/") + "/#studio")
    pg.wait_for_selector("#mainNav", timeout=15000); pg.wait_for_timeout(2500)
    ok(f"{name}: app reports started", pg.evaluate("window.__zeimStarted === true && window.__zeimEditStarted === true"))
    ok(f"{name}: no error banner on a healthy page", not pg.is_visible("#bootError"))
    for v in ("showcase", "slicer", "cad", "smartfix", "account", "lithophane"):
        pg.click(f"#mainNav [data-view={v}]"); pg.wait_for_timeout(500)
    pg.click("#sSample"); pg.wait_for_selector("#result:not([hidden])", timeout=120000); pg.wait_for_timeout(500)
    ok(f"{name}: no page errors / console errors on a normal session (4 tabs + a sample build)", not errs, errs[:3])
    ctx.close()
    # 2. broken scripts are announced
    for label, handler in (("edit.js throws", lambda r: r.fulfill(status=200, content_type="text/javascript", body='throw new Error("boom");')),
                           ("app.js is a 404", lambda r: r.fulfill(status=404, body="nope"))):
        target = "**/static/edit.js" if "edit" in label else "**/static/app.js"
        ctx, pg, errs = page(lambda c, t=target, h=handler: c.route(t, lambda r: h(r)))
        pg.goto(URL.rstrip("/") + "/#studio"); pg.wait_for_timeout(2500)
        vis = pg.is_visible("#bootError")
        ok(f"{name}: {label} -> a visible message with a Reload button", vis and pg.is_visible("#bootError button"), pg.inner_text("#bootError") if vis else "(no banner)")
        ctx.close()
    b.close()

with sync_playwright() as p:
    run("chrome", lambda: p.chromium.launch(channel="chrome"))
    run("webkit", lambda: p.webkit.launch())
sys.exit(0 if all(R) and R else 1)
