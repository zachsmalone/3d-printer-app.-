"""Recent builds: the star keeps a build (>= 44px, aria-pressed, survives reload), the 7-day note is shown.  390px, Chrome + WebKit.
python tests/ui_favs.py URL"""
import sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1]
bad = []
def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, x)
    if not c: bad.append(n)
MK = """async () => { const sb = await (await fetch('/static/sample.png')).blob(); const fd = new FormData(); fd.append('file', new File([sb], 'a.png', {type:'image/png'}));
  fd.append('mode','relief'); fd.append('resolution','40'); fd.append('width_mm','40'); const r = await fetch('/api/generate', {method:'POST', body: fd}); return r.status; }"""
def run(name, launch):
    try: b = launch()
    except Exception as e: print(f"SKIP {name}: {str(e).splitlines()[0][:80]}"); return
    errs = []
    ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
    pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL.rstrip("/") + "/#studio"); pg.wait_for_timeout(600); pg.evaluate(MK); pg.reload(); pg.wait_for_selector("#histList .hcard", timeout=15000)
    ok(f"{name}: the 7-day note and the 0/20 style count are shown", "7 days" in pg.inner_text("#histNote") and "/ 20" in pg.inner_text("#histCount"), (pg.inner_text("#histNote"), pg.inner_text("#histCount")))
    star = pg.locator("#histList .hcard button.star").first
    box = star.bounding_box(); ok(f"{name}: star is >= 44px", box["width"] >= 44 and box["height"] >= 44, box)
    ok(f"{name}: not starred at first", star.get_attribute("aria-pressed") == "false")
    star.click(); pg.wait_for_timeout(800)
    ok(f"{name}: starring is announced (aria-pressed=true)", pg.locator("#histList .hcard button.star").first.get_attribute("aria-pressed") == "true")
    pg.reload(); pg.wait_for_selector("#histList .hcard"); ok(f"{name}: the star survives a reload", pg.locator("#histList .hcard button.star").first.get_attribute("aria-pressed") == "true")
    ok(f"{name}: no page errors", not errs, errs)
    ctx.close(); b.close()
with sync_playwright() as p:
    run("chrome", lambda: p.chromium.launch(channel="chrome"))
    run("webkit", lambda: p.webkit.launch())
sys.exit(1 if bad else 0)
