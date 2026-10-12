"""Print dialog: Creality Cloud first on phones (390x844), desktop slicer links demoted; no link/deep link for Creality; 44 px targets.
python tests/ui_creality.py URL_WITH_SHARE_FLAG URL_WITHOUT   (Chrome + WebKit). Headless only: NOT the real iOS share sheet, NOT the Creality app."""
import sys
from playwright.sync_api import sync_playwright
U1, U2 = sys.argv[1], sys.argv[2]
R = []
def ok(n, c, x=""): R.append(bool(c)); print(("PASS " if c else "FAIL ") + n, x)
STUB = """window.__shared=[];
navigator.canShare=d=>!!(d&&d.files&&d.files.length&&d.files[0].name==='ZEIM-build.3mf'&&!('url' in d));
navigator.share=async d=>{window.__shared.push({n:d.files.map(f=>f.name+':'+f.size),keys:Object.keys(d)});};"""

def open_print(b, url, phone, stub=False):
    ctx = b.new_context(viewport={"width": 390, "height": 844} if phone else {"width": 1280, "height": 900}, has_touch=phone)
    pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    if stub: pg.add_init_script(STUB)
    pg.goto(url.rstrip("/") + "/#studio"); pg.wait_for_selector("#mainNav", timeout=15000); pg.wait_for_timeout(800)
    pg.click("#sSample"); pg.wait_for_selector("#result:not([hidden])", timeout=120000); pg.wait_for_timeout(500)
    pg.click("#btnPrint"); pg.wait_for_selector("#dlgPrint[open]"); pg.wait_for_timeout(700)
    return ctx, pg, errs

def run(name, launch):
    try: b = launch()
    except Exception as e: print(f"SKIP {name}: {str(e).splitlines()[0][:80]}"); return
    # ---- phone, share flag OFF
    ctx, pg, errs = open_print(b, U2, True)
    first = pg.evaluate("document.querySelector('#slicerBtns').firstElementChild.className")
    ok(f"{name} phone: the Creality Cloud block is the first thing under 'Open in your slicer'", "cre" in first, first)
    ok(f"{name} phone: starred 'Download 3MF' is the primary button", "★" in pg.inner_text("#crDl") and pg.get_attribute("#crDl", "download") == "ZEIM-build.3mf")
    href = pg.get_attribute("#crDl", "href"); bid = href.split("/")[2]
    ok(f"{name} phone: it is the authenticated download (/files/<id>/model.3mf), not a link", href.startswith("/files/") and href.endswith("/model.3mf") and "token" not in href, href)
    hrefs = pg.eval_on_selector_all(".cre a", "els=>els.map(e=>e.getAttribute('href'))")
    ok(f"{name} phone: nothing in the Creality block is an external or deep link", all(h.startswith("/files/") for h in hrefs), hrefs)
    steps = pg.inner_text(".cre-steps")
    ok(f"{name} phone: steps say Download, then Share / Open in… > Creality", "Download 3MF" in steps and "Share" in steps and "Creality" in steps)
    ok(f"{name} phone: experimental wording kept, no invented claim", "experimental" in pg.inner_text(".cre") and "does not connect to Creality" in pg.inner_text(".cre"))
    ok(f"{name} phone: no Share button when the share flag is off", pg.locator("#crShare").count() == 0)
    d = pg.locator("details.slicers-more")
    ok(f"{name} phone: 'On a computer' is collapsed and PrusaSlicer/Bambu/Orca/Cura are hidden in it", d.count() == 1 and not d.evaluate("e=>e.open")
       and not pg.locator("details.slicers-more a:has-text('PrusaSlicer')").first.is_visible())
    d.locator("summary").click(); pg.wait_for_timeout(200)
    ok(f"{name} phone: opening it shows the desktop slicers", pg.locator("details.slicers-more a:has-text('PrusaSlicer')").first.is_visible())
    small = pg.evaluate("""[...document.querySelectorAll('#dlgPrint a.btn, #dlgPrint button, #dlgPrint summary, #dlgPrint input[type=checkbox]')]
        .filter(e=>e.offsetParent!==null && !e.closest('[hidden]')).map(e=>{const t=e.matches('input')?(e.closest('label')||e):e;return [t.textContent.trim().slice(0,25)||e.id, t.getBoundingClientRect().height]}).filter(x=>x[1]<44)""")
    ok(f"{name} phone: every visible button/link/summary is >= 44 px tall", not small, small)
    ok(f"{name} phone: no page errors", not errs, errs)
    ctx.close()
    # ---- phone, share flag ON (stubbed share sheet)
    ctx, pg, errs = open_print(b, U1, True, stub=True)
    pg.wait_for_selector("#crShare:not([disabled])", timeout=15000)
    pg.click("#crShare"); pg.wait_for_timeout(400)
    sh = pg.evaluate("window.__shared")
    ok(f"{name} phone+share: Share hands over ONE real file named ZEIM-build.3mf, files+title only, no url", len(sh) == 1 and sh[0]["n"][0].startswith("ZEIM-build.3mf:") and sorted(sh[0]["keys"]) == ["files", "title"], sh)
    ok(f"{name} phone+share: no page errors", not errs, errs)
    ctx.close()
    # ---- desktop
    ctx, pg, errs = open_print(b, U2, False)
    ok(f"{name} desktop: plain 'Download 3MF for Creality Print' button, no deep link", "Creality Print" in pg.inner_text("#crDl") and pg.get_attribute("#crDl", "href").startswith("/files/"))
    ok(f"{name} desktop: slicer deep links still shown, not collapsed", pg.locator("#slicerBtns a:has-text('PrusaSlicer')").first.is_visible() and pg.locator("details.slicers-more").count() == 0)
    ok(f"{name} desktop: no page errors", not errs, errs)
    ctx.close(); b.close()

with sync_playwright() as p:
    run("chrome", lambda: p.chromium.launch(channel="chrome"))
    run("webkit", lambda: p.webkit.launch())
sys.exit(0 if all(R) and R else 1)
