"""Nozzle it in a real browser: states, names, keyboard, in-place sync card<->dialog, rollback, double-tap, signed-out dialog, own project,
no hearts/likes words, axe (Chrome).  390px, Chrome + WebKit.   python tests/ui_nozzle.py URL  (TEMP-data server)"""
import json, os, re, sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PNG = open(os.path.join(ROOT, "static", "sample.png"), "rb").read()
AXE = os.environ.get("AXE_JS") or "/workspace/a11y-tools/node_modules/axe-core/axe.min.js"
bad = []
def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c: bad.append(n)

def axe(pg, label):
    if not os.path.exists(AXE): return
    pg.add_script_tag(path=AXE)
    r = pg.evaluate("axe.run(document, {runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','best-practice']}}).then(r=>r.violations.map(v=>({id:v.id,n:v.nodes.length,t:v.nodes.slice(0,3).map(n=>n.target.join(' '))})))")
    ok(f"axe: {label}", not r, json.dumps(r)[:700])

def publish(r, title):
    g = r.post(URL + "/api/generate", multipart={"file": {"name": "a.png", "mimeType": "image/png", "buffer": PNG}, "mode": "relief", "photo_ack": "true"}).json()
    return r.post(URL + "/api/showcase", data={"build_id": g["id"], "title": title, "description": "", "tags": [], "accept_guidelines": True, "visibility": "public"}).json()["id"]

def run(name, launch, with_axe):
    try: b = launch()
    except Exception as e: print(f"SKIP {name}: {str(e).splitlines()[0][:80]}"); return
    tag = name[:2]; errs = []
    owner = b.new_context(bypass_csp=True); r = owner.request
    r.post(URL + "/api/me/signup", data={"display_name": "Ada", "dob": "1985-05-05"})
    iid = publish(r, f"Fox {tag}")
    def page(ctx):
        pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e))); pg.goto(URL.rstrip("/") + "/#studio"); pg.wait_for_timeout(700)
        pg.click("#mainNav [data-view=showcase]"); pg.wait_for_selector("#shGrid .pcard", timeout=15000); return pg
    nz = lambda pg: pg.locator(f'#shGrid .nz[data-nz="{iid}"]')
    ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True, bypass_csp=True)
    pg = page(ctx)
    btn = nz(pg)
    ok(f"{name}: a real project has a Nozzle it button, name with the count rule, aria-pressed=false", btn.count() == 1 and btn.get_attribute("aria-pressed") == "false"
       and btn.get_attribute("aria-label") in ("Nozzle it, no nozzles yet", "Nozzle it, 0 nozzles"), btn.get_attribute("aria-label"))
    ok(f"{name}: no '0' is shown to the child", btn.locator(".nz-count").inner_text() == "")
    ok(f"{name}: no EXAMPLE cards remain", pg.locator("#shGrid .pcard:has(.ex)").count() == 0)
    bb = btn.bounding_box(); ok(f"{name}: button is at least 44x44", bb["width"] >= 43.5 and bb["height"] >= 43.5, bb)
    ok(f"{name}: each card's title is a link and the card is a list item", pg.locator("#shGrid > li.pcard h2 a").count() >= 1)
    ok(f"{name}: no hearts, likes or downvote words on the Showcase", not re.search(r"♥|❤|dislike|downvote|\\blikes?\\b", pg.inner_text("#viewShowcase"), re.I))
    # signed out
    btn.click(); pg.wait_for_selector("#dlgNzAcct[open]")
    ok(f"{name}: signed-out press opens 'Make a free account to nozzle'", "Make a free account to nozzle" in pg.inner_text("#dlgNzAcct") and btn.get_attribute("aria-pressed") == "false")
    if with_axe: axe(pg, "signed-out dialog")
    pg.click("#nzAcctLater"); pg.wait_for_timeout(150)
    ok(f"{name}: Not now closes and returns focus to the button", not pg.is_visible("#dlgNzAcct") and pg.evaluate("document.activeElement.dataset.nz") == iid)
    if with_axe: axe(pg, "Showcase grid with nozzle buttons, 390 light")
    # make an account through the real sign-up dialog -> announced
    btn.click(); pg.wait_for_selector("#dlgNzAcct[open]"); pg.click("#nzAcctMake"); pg.wait_for_selector("#dlgAccount[open]")
    pg.fill("#su_name", "Vi"); pg.fill("#su_user", f"Viewer_{tag}{os.getpid() % 9973}"); pg.fill("#su_dob", "1990-01-01"); pg.click("#su_go"); pg.wait_for_selector("#un_now", timeout=8000); pg.wait_for_timeout(400)
    ok(f"{name}: after sign-up the page says nozzling is possible, in place", "can nozzle projects now" in pg.inner_text("#nzStatus"))
    pg.evaluate("document.querySelector('#dlgAccount').close()")
    pg.evaluate("document.querySelector('#shGrid').dataset.mark = '1'"); marker = pg.evaluate("document.querySelector('#shGrid .pcard').dataset.m = 'keep'")
    btn = nz(pg); btn.focus(); pg.keyboard.press("Space"); pg.wait_for_timeout(500)
    ok(f"{name}: Space nozzles: pressed, name '1 nozzle', polite status, focus stays", btn.get_attribute("aria-pressed") == "true" and btn.get_attribute("aria-label") == "Nozzle it, 1 nozzle"
       and "Nozzled. 1 nozzle." in pg.inner_text("#nzStatus") and pg.evaluate("document.activeElement.dataset.nz") == iid)
    ok(f"{name}: the card was updated in place (not rebuilt)", pg.evaluate("document.querySelector('#shGrid .pcard').dataset.m") == "keep")
    pg.keyboard.press("Enter"); pg.wait_for_timeout(500)
    ok(f"{name}: Enter takes it back: not pressed, 'Nozzle removed.'", btn.get_attribute("aria-pressed") == "false" and "Nozzle removed." in pg.inner_text("#nzStatus"))
    # dialog <-> card sync
    pg.locator(f'#shGrid .pcard:has(.nz[data-nz="{iid}"]) h2 a').click(); pg.wait_for_selector("#dlgItem[open]"); pg.wait_for_timeout(300)
    big = pg.locator(f'#dlgItem .nz[data-nz="{iid}"]')
    ok(f"{name}: the project dialog has the large 'Nozzle it' button", big.count() == 1 and "Nozzle it" in big.inner_text() and big.bounding_box()["height"] >= 43.5)
    big.click(); pg.wait_for_timeout(500)
    ok(f"{name}: pressing in the dialog also updates the card behind it", nz(pg).get_attribute("aria-pressed") == "true" and big.get_attribute("aria-pressed") == "true" and pg.evaluate("document.querySelector('#dlgItem').open"))
    ok(f"{name}: dialog keeps focus on the button", pg.evaluate("document.activeElement.dataset.nz") == iid)
    if with_axe: axe(pg, "item dialog with pressed nozzle")
    # failure rolls back
    pg.route("**/like", lambda route: route.abort())
    big.click(); pg.wait_for_timeout(700)
    ok(f"{name}: a failed save rolls back and raises an alert", big.get_attribute("aria-pressed") == "true" and nz(pg).get_attribute("aria-pressed") == "true" and "Couldn't save your nozzle" in pg.inner_text("#nzAlert"), pg.inner_text("#nzAlert"))
    pg.unroute("**/like")
    # double tap: one request, consistent end
    hits = []
    pg.route("**/like", lambda route: (hits.append(route.request.post_data), route.continue_()))
    big.dblclick(); pg.wait_for_timeout(800)
    ok(f"{name}: a double tap sends one request with an explicit state", len(hits) == 1 and '"liked"' in hits[0], hits)
    pg.unroute("**/like")
    pg.keyboard.press("Escape")
    # own project
    op = page(owner.browser.new_context(viewport={"width": 390, "height": 844}, bypass_csp=True)) if False else None
    ctx.close()
    oc = b.new_context(viewport={"width": 390, "height": 844}, bypass_csp=True); oc.request.post(URL + "/api/me/signup", data={"display_name": "Own", "dob": "1985-05-05"})
    own_id = publish(oc.request, f"Mine {tag}")
    po = page(oc)
    card = po.locator(f'#shGrid .pcard:has(h2 a[data-open="{own_id}"])')
    ok(f"{name}: your own project shows static text, not a button", card.locator(".nz").count() == 0 and card.locator(".nz-static").count() == 1)
    oc.close()
    ok(f"{name}: no page errors", not errs, errs)
    owner.close(); b.close()

with sync_playwright() as p:
    run("chrome", lambda: p.chromium.launch(channel="chrome"), True)
    run("webkit", lambda: p.webkit.launch(), False)
sys.exit(1 if bad else 0)
