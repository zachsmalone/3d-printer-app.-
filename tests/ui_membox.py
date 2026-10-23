"""Memory box in the Lithophane workspace: 3 styles + base preview, sample fill, export picker. python tests/ui_membox.py URL [SHOTDIR]"""
import os, sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1].rstrip("/"); SHOTS = sys.argv[2] if len(sys.argv) > 2 else "/workspace/qa/membox-sample/shots"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.makedirs(SHOTS, exist_ok=True); bad = []
ROSES = [f"/static/samples/membox/rose{i}.jpg" for i in range(1, 5)]
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
        def build(st):
            pg.select_option("#mbStyle", st); pg.click("#mbPreview")
            for _ in range(600):
                t = pg.inner_text("#mbStatus")
                if not t.startswith("Making"): break
                pg.wait_for_timeout(250)
            return t
        # Not using the sample box: one own photo, Tango fills sides 2-4
        pg.set_input_files("#mbFiles", [os.path.join(ROOT, "tests", "sample.png")]); pg.check("#mbAck")
        ok(f"{name}: one photo shows on side 1 only", pg.locator("#mbSides img[src]").count() == 1)
        t = build("frame")
        ok(f"{name}: Tango fills empty sides ({t[:60]})", t.startswith("Parts") and "Sample photo on side 2, 3, 4" in pg.inner_text("#mbDims"))
        pg.uncheck("#mbAck")
        # Try the sample box: 4 roses into sides 1-4 in one tap
        btn = pg.locator("#mbTrySample"); btn.scroll_into_view_if_needed()
        ok(f"{name}: sample box button, line icon, no emoji", btn.is_visible() and btn.locator("svg").count() == 1
           and "Try the sample box" in btn.inner_text() and all(ord(ch) < 0x2190 for ch in btn.inner_text()))
        pg.locator("#mboxBox .mbsample").screenshot(path=f"{SHOTS}/sample-button-{name}.png")
        btn.click()
        for _ in range(60):
            if pg.locator("#mbSides img[src]").count() == 4: break
            pg.wait_for_timeout(250)
        srcs = pg.evaluate("[...document.querySelectorAll('#mbSides img')].map(i => i.naturalWidth > 0)")
        ok(f"{name}: sample loads 4 roses on sides 1-4", srcs == [True] * 4 and "Sample box loaded" in pg.inner_text("#mbStatus"))
        def overlap():
            return pg.evaluate("""() => { const r = [...document.querySelectorAll('#mbSides li, #mbTrySample, #mbSampleHelp')].map(e => e.getBoundingClientRect());
              for (let i = 0; i < r.length; i++) for (let j = i + 1; j < r.length; j++) { const a = r[i], b = r[j];
                if (a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1) return true; } return false; }""")
        ok(f"{name}: sample row and side thumbnails do not overlap", not overlap())
        pg.locator("#mbSides").screenshot(path=f"{SHOTS}/sample-loaded-{name}.png")
        # replace side 2 with an own photo, then put the rose back via the sample button
        with pg.expect_file_chooser() as fc: pg.click("#mbSides button[data-side='2']")
        fc.value.set_files(os.path.join(ROOT, "tests", "sample.png"))
        ok(f"{name}: side 2 replaceable", pg.locator("#mbSides img[src]").count() == 4)
        pg.click("#mbTrySample"); pg.wait_for_timeout(800)
        ok(f"{name}: tolerance note", "can change it" in pg.inner_text("#mbClearHelp"))
        for st in ("frame", "snap", "enclosed"):
            t = build(st)
            ok(f"{name}: {st} built ({t[:80]})", t.startswith("Parts") and f"{st}" in (pg.inner_text("#mbStatus") + st))
            pg.wait_for_timeout(600)
            ok(f"{name}: {st} preview has light base", "light_base" in pg.inner_text("#mbStatus"))
            ok(f"{name}: {st} dims shown", pg.is_visible("#mbDims") and "Cable notch: 8 mm" in pg.inner_text("#mbDims")
               and "Sample photo" not in pg.inner_text("#mbDims"))
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
