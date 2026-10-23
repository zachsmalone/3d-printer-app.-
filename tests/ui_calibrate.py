"""Calibration wizard in a real browser (Chrome + WebKit), phone width: open from Smart Fix, four tests listed,
STL links, slicing the temperature tower shows the bands and a G-code download, resin printer shows the resin note.
python tests/ui_calibrate.py URL"""
import sys
from playwright.sync_api import sync_playwright
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__))); import zws_open; zws_open.install()   # C: phone panels start as chips
URL = sys.argv[1].rstrip("/"); bad = []


def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c: bad.append(n)


def run(name, launch):
    b = launch(); ctx = b.new_context(viewport={"width": 390, "height": 844}); pg = ctx.new_page()
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL + "/#smartfix"); pg.wait_for_timeout(800)
    pg.click("#calOpen")
    pg.wait_for_selector("#calPlan .caltest", timeout=30000)
    ok(f"{name}: four tests", pg.locator("#calPlan .caltest").count() == 4, pg.inner_text("#calPlan"))
    ok(f"{name}: plain steps + estimate note", "Clean the bed" in pg.inner_text("#calPlan") and "estimates" in pg.inner_text("#calPlan"))
    ok(f"{name}: printer + filament pickers labelled", pg.locator("label[for=cal_pr]").count() == 1 and pg.locator("label[for=calMat]").count() == 1)
    hrefs = pg.eval_on_selector_all("#calPlan a[download]", "a => a.map(x => x.getAttribute('href'))")
    ok(f"{name}: STL link per test", len(hrefs) == 4 and all("/api/calibration/" in h and ".stl?" in h for h in hrefs), hrefs)
    pg.click("#cal_temp_tower summary")
    pg.click("[data-calslice=temp_tower]")
    pg.wait_for_selector("#calout_temp_tower .slicestats, #calout_temp_tower [role=alert]", timeout=120000)
    t = pg.inner_text("#calout_temp_tower")
    ok(f"{name}: tower sliced with bands", "220 °C" in t and "195 °C" in t and pg.locator("#calout_temp_tower a[href$='/gcode']").count() == 1, t)
    pg.select_option("#calMat", "ABS")
    pg.wait_for_selector("#calPlan .matwarn", timeout=20000)
    pg.click("#cal_flow summary")
    pg.click("[data-calslice=flow]")
    pg.wait_for_selector("#calout_flow [role=alert]", timeout=20000)
    ok(f"{name}: ABS asks about ventilation first", "ventilat" in pg.inner_text("#calout_flow").lower(), pg.inner_text("#calout_flow"))
    pg.select_option("#cal_pr", "elegoo_mars4")
    pg.wait_for_function("() => /resin printer/.test(document.querySelector('#calPlan').textContent)", timeout=20000)
    ok(f"{name}: resin note with safety", "gloves" in pg.inner_text("#calPlan"))
    sz = pg.evaluate("[...document.querySelectorAll('#calBox button, #calBox select')].filter(b => b.offsetParent).map(b => Math.min(b.getBoundingClientRect().width, b.getBoundingClientRect().height))")
    ok(f"{name}: controls are 44 px targets", all(v >= 44 for v in sz), sz)
    ok(f"{name}: no page errors", not errs, errs)
    b.close()
    if not bad: print(f"PASS {name}")


with sync_playwright() as p:
    run("chrome", lambda: p.chromium.launch())
    run("webkit", lambda: p.webkit.launch())
sys.exit(1 if bad else 0)
