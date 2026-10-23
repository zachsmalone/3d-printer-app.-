"""Memory box in the Lithophane workspace: 3 styles + base preview, sample fill, export picker. python tests/ui_membox.py URL [SHOTDIR]"""
import os, sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1].rstrip("/"); SHOTS = sys.argv[2] if len(sys.argv) > 2 else "/workspace/qa/membox/shots"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.makedirs(SHOTS, exist_ok=True); bad = []
def ok(n, c):
    print(("PASS " if c else "FAIL ") + n); c or bad.append(n)
with sync_playwright() as p:
    b = p.chromium.launch()
    for name, vp, kw in (("w1280", {"width": 1280, "height": 900}, {}), ("w390", {"width": 390, "height": 844}, {"has_touch": True, "is_mobile": True, "device_scale_factor": 2})):
        pg = b.new_page(viewport=vp, **kw); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script("localStorage.level='expert'")
        pg.goto(URL + "/#studio"); pg.wait_for_timeout(1500)
        box = pg.locator("#mboxBox"); box.scroll_into_view_if_needed()
        if not box.get_attribute("open"): pg.click("#mboxBox > summary")
        ok(f"{name}: memory box option visible", pg.is_visible("#mbStyle") and pg.is_visible("#mbSample"))
        ok(f"{name}: line icon, no emoji in summary", box.locator("summary svg").count() == 1)
        pg.set_input_files("#mbFiles", [os.path.join(ROOT, "tests", "sample.png")])
        pg.check("#mbAck")
        ok(f"{name}: tolerance note", "can change it" in pg.inner_text("#mbClearHelp"))
        for st in ("frame", "snap", "enclosed"):
            pg.select_option("#mbStyle", st)
            pg.click("#mbPreview")
            for _ in range(600):
                t = pg.inner_text("#mbStatus")
                if not t.startswith("Making"): break
                pg.wait_for_timeout(250)
            ok(f"{name}: {st} built ({t[:80]})", t.startswith("Parts") and f"{st}" in (pg.inner_text("#mbStatus") + st))
            pg.wait_for_timeout(600)
            ok(f"{name}: {st} preview has light base", "light_base" in pg.inner_text("#mbStatus"))
            ok(f"{name}: {st} dims shown", pg.is_visible("#mbDims") and "Cable notch: 8 mm" in pg.inner_text("#mbDims")
               and "Sample photo on side 2, 3, 4" in pg.inner_text("#mbDims"))
            pg.locator("#viewer").scroll_into_view_if_needed()
            pg.locator("#viewer").screenshot(path=f"{SHOTS}/{st}-{name}.png")
        pg.locator("#mbDims").screenshot(path=f"{SHOTS}/base-dims-{name}.png")
        ok(f"{name}: export enabled", pg.is_enabled("#mbExport"))
        pg.click("#mbExport")
        pg.wait_for_selector("#dlgExport[open]", timeout=15000); pg.wait_for_timeout(500)
        nm = pg.inner_text("#expNameOut")
        ok(f"{name}: export picker name {nm!r}", nm.startswith("Memory box - ") and "0.2mm" in nm)
        ok(f"{name}: picker offers STL and 3MF", pg.locator("input[name=expFmt][value=stl]").count() == 1 and pg.locator("input[name=expFmt][value='3mf']").count() == 1)
        pg.locator("#dlgExport").screenshot(path=f"{SHOTS}/export-{name}.png")
        pg.click("#expCancel")
        sw = pg.evaluate("document.documentElement.scrollWidth")
        ok(f"{name}: no sideways scroll ({sw})", sw <= vp["width"] + 1)
        ok(f"{name}: no page errors {errs}", not errs)
    b.close()
sys.exit(1 if bad else 0)
