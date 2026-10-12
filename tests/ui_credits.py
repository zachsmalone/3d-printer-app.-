"""Credits page + footer link + Showcase credit line at phone width (390px), Chrome and WebKit.
python tests/ui_credits.py URL   (WebKit-on-Linux headless; NOT a real iPhone)"""
import sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1]
def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, x)
    if not c: sys.exit_code = 1
sys.exit_code = 0

def run(name, launch):
    try:
        b = launch()
    except Exception as e:
        print(f"SKIP {name}: cannot launch ({str(e).splitlines()[0][:80]})"); return
    errs = []
    ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
    pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL); pg.wait_for_timeout(600)
    link = pg.locator(".sitefoot a[href='/credits']"); link.scroll_into_view_if_needed()
    box = link.bounding_box()
    ok(f"{name}: footer 'Thank you & credits' link is there and >= 44px tall", box and box["height"] >= 44 and "credits" in link.inner_text().lower(), box)
    link.click(); pg.wait_for_url("**/credits"); pg.wait_for_timeout(400)
    ok(f"{name}: /credits has a single h1", pg.locator("h1").count() == 1)
    ok(f"{name}: page does not scroll sideways at 390px", pg.evaluate("document.documentElement.scrollWidth") <= 390, pg.evaluate("document.documentElement.scrollWidth"))
    ok(f"{name}: PrusaSlicer and trimesh are listed", "PrusaSlicer" in pg.inner_text("body") and "trimesh" in pg.inner_text("body"))
    ok(f"{name}: trademark line and 'Coming soon' placeholders present", "not affiliated" in pg.inner_text("body") and "Coming soon" in pg.inner_text("body"))
    small = [t for t in pg.locator("main a, details.maker summary, a.home").evaluate_all("els => els.map(e => [e.textContent.trim().slice(0,30), e.getBoundingClientRect().height, getComputedStyle(e).display])") if t[1] and t[1] < 44 and t[2] != "inline"]
    ok(f"{name}: block-level links/summaries on /credits are >= 44px", not small, small)
    ok(f"{name}: external links are noopener", pg.locator("a[href^='http']:not([rel*='noopener'])").count() == 0)
    # Showcase: example item has no fake download; credit line / creator link present
    pg.goto(URL); pg.wait_for_timeout(500); pg.click("#mainNav [data-view=showcase]"); pg.wait_for_selector("#shGrid .pcard", timeout=15000)
    pg.click('#shGrid .pcard[data-item="zo-pencil-cup"] h2 a'); pg.wait_for_selector("#dlgItem[open]", timeout=8000); pg.wait_for_timeout(300)
    txt = pg.inner_text("#dlgItem")
    ok(f"{name}: an Original shows its credit line, Untested print and a real .stl download", '"Pencil Cup" by ZEIM' in txt and "Untested print" in txt and pg.locator("#dlgItem a[download][href$='.stl']").count() == 1, txt[:200])
    ok(f"{name}: dialog has no sideways scroll", pg.evaluate("document.querySelector('#dlgItem').scrollWidth <= document.querySelector('#dlgItem').clientWidth + 1"))
    ok(f"{name}: no page errors", not errs, errs)
    ctx.close(); b.close()

with sync_playwright() as p:
    run("chrome", lambda: p.chromium.launch(channel="chrome"))
    run("webkit", lambda: p.webkit.launch())
sys.exit(sys.exit_code)
