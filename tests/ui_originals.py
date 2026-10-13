"""Originals-first Showcase in the browser: cards show credit, difficulty, Suggested FDM, Untested print, caveats and a working STL link;
category chips filter. 390px, Chrome + WebKit (axe in Chrome)."""
import json, os, sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1]; bad = []
AXE = os.environ.get("AXE_JS") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "axe.min.js")
def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c: bad.append(n)
def cards(pg): return pg.locator("#shGrid .pcard h2 a").all_inner_texts()
def run(name, launch, with_axe):
    try: b = launch()
    except Exception as e: print(f"SKIP {name}: {str(e).splitlines()[0][:80]}"); return
    errs = []
    ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True, bypass_csp=True)   # lets the vendored axe script load under the app CSP
    pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL.rstrip("/") + "/#studio"); pg.wait_for_timeout(700); pg.click("#mainNav [data-view=showcase]"); pg.click('#shTabs [data-tab=free]')
    pg.wait_for_selector('#shGrid .pcard[data-item="zo-pencil-cup"]')
    t = pg.inner_text('#shGrid .pcard[data-item="zo-pencil-cup"]')
    ok(f"{name}: card shows credit, difficulty, Suggested FDM, Untested print, caveat", all(s in t for s in ('"Pencil Cup" by ZEIM · CC BY 4.0', "Easy", "Suggested: FDM", "Untested print", "Fit not checked")), t)
    ok(f"{name}: no EXAMPLE cards left", "EXAMPLE" not in pg.inner_text("#shGrid"))
    href = pg.get_attribute('#shGrid .pcard[data-item="zo-pencil-cup"] a[download]', "href")
    r = ctx.request.get(URL + href)
    ok(f"{name}: STL link downloads the file", r.status == 200 and len(r.body()) > 100, (href, r.status))
    ok(f"{name}: preview image loads", pg.evaluate("[...document.querySelectorAll('#shGrid .pcard img')].every(i => i.complete && i.naturalWidth > 0)"))
    pg.click('#shCats [data-cat="Wildlife Calls"]'); pg.wait_for_selector('#shCats [data-cat="Wildlife Calls"][aria-pressed=true]')
    pg.wait_for_timeout(300)
    ok(f"{name}: category chip filters", sorted(cards(pg)) == ["Open-Reed Predator Call", "Owl Whistle"], cards(pg))
    ok(f"{name}: chips are 44px tall", pg.locator('#shCats [data-cat=""]').bounding_box()["height"] >= 43.5)
    if with_axe:
        assert os.path.exists(AXE), "axe missing: " + AXE
        pg.add_script_tag(path=AXE)
        v = pg.evaluate("axe.run(document.querySelector('#shGrid').closest('section') || document, {runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}}).then(r=>r.violations.map(v=>({id:v.id,n:v.nodes.length,t:v.nodes.slice(0,3).map(n=>n.target.join(' '))})))")
        ok(f"{name}: axe on the Showcase", not v, json.dumps(v)[:800])
    pg.click('#shCats [data-cat=""]'); pg.wait_for_timeout(300)
    ok(f"{name}: no page errors", not errs, errs)
    ctx.close(); b.close()
with sync_playwright() as p:
    run("chrome", lambda: p.chromium.launch(channel="chrome"), True)
    run("webkit", lambda: p.webkit.launch(), False)
sys.exit(1 if bad else 0)
