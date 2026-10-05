"""Settings sheet on a phone: the API-key (password) field and the other text fields are readable (contrast >= 4.5:1) with >= 16px text; default-slicer choices.  390px, Chrome + WebKit.
python tests/ui_settings.py URL"""
import sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1]
bad = []
def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, x)
    if not c: bad.append(n)
LUM = "(() => { const e = document.querySelector(%r); const L = c => { const f = v => { v /= 255; return v <= 0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); }; return 0.2126*f(c[0])+0.7152*f(c[1])+0.0722*f(c[2]); }; const st = getComputedStyle(e); const bg = st.backgroundColor.match(/[\\d.]+/g).map(Number), fg = st.color.match(/[\\d.]+/g).map(Number); const a = L(bg), b = L(fg); return [(Math.max(a,b)+0.05)/(Math.min(a,b)+0.05), parseFloat(st.fontSize), e.getBoundingClientRect().height]; })()"

def run(name, launch):
    try: b = launch()
    except Exception as e: print(f"SKIP {name}: {str(e).splitlines()[0][:80]}"); return
    errs = []
    ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
    pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL); pg.wait_for_timeout(700)
    pg.click("#btnSettings"); pg.wait_for_selector("#dlgSettings[open]"); pg.click("#btnAddPrinter"); pg.wait_for_selector("#printerList [data-f=api_key]")
    lum, fs, h = pg.evaluate(LUM % "#printerList [data-f=api_key]")
    ok(f"{name}: API key field is readable (contrast {lum:.1f}:1), >= 16px, >= 44px tall", lum >= 4.5 and fs >= 16 and h >= 44, (lum, fs, h))
    opts = pg.eval_on_selector_all("#set_slicer option", "els => els.map(e => e.textContent)")
    ok(f"{name}: default slicer list has Creality Print / Creality Cloud and Automatic", any("Creality Print" in o for o in opts) and any("Automatic" in o for o in opts), opts)
    types = pg.eval_on_selector_all("#printerList [data-f=type] option", "els => els.map(e => e.textContent)")
    ok(f"{name}: not-yet-built printer types say Coming soon, none say 'stub'", any("Coming soon" in t for t in types) and not any("stub" in t.lower() for t in types), types)
    ok(f"{name}: settings sheet does not scroll sideways", pg.evaluate("document.querySelector('#dlgSettings .dlg').scrollWidth <= document.querySelector('#dlgSettings .dlg').clientWidth + 1"))
    pg.click("#dlgSettings [data-close]"); pg.click("#btnAccount"); pg.wait_for_selector("#su_dob")
    lum, fs, h = pg.evaluate(LUM % "#su_dob"); ok(f"{name}: date-of-birth field is readable (>= 4.5:1) and >= 16px", lum >= 4.5 and fs >= 16, (lum, fs, h))
    ok(f"{name}: no page errors", not errs, errs)
    ctx.close(); b.close()

with sync_playwright() as p:
    run("chrome", lambda: p.chromium.launch(channel="chrome"))
    run("webkit", lambda: p.webkit.launch())
sys.exit(1 if bad else 0)
