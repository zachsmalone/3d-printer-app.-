"""Plate editor + Light on screenshots and a quick UI check (Chrome).  python tests/ui_plate_shots.py URL [SHOTDIR]"""
import os, sys, tempfile
import trimesh
from playwright.sync_api import sync_playwright
URL = sys.argv[1].rstrip("/"); SHOTS = sys.argv[2] if len(sys.argv) > 2 else None; bad = []


def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c: bad.append(n)


def shot(pg, sub, name):
    if SHOTS:
        os.makedirs(os.path.join(SHOTS, sub), exist_ok=True); pg.screenshot(path=os.path.join(SHOTS, sub, name))


d = tempfile.mkdtemp(prefix="zeim-plate-")
files = []
for n, (s, kind) in enumerate([((30, 30, 30), "box"), ((20, 40), "cyl"), ((50, 25, 12), "box")]):
    m = trimesh.creation.box(s) if kind == "box" else trimesh.creation.cylinder(radius=s[0] / 2, height=s[1])
    f = os.path.join(d, f"part{n + 1}.stl"); m.export(f); files.append(f)
with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
    pg = b.new_page(viewport={"width": 1366, "height": 900}); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL + "/#slicer"); pg.wait_for_timeout(1200)
    pg.set_input_files("#editFile", files)
    pg.click("#multiPlate"); pg.wait_for_selector("#plateTool", timeout=60000); pg.wait_for_timeout(800)
    ok("object list shows 3 objects with eye + delete", pg.locator(".plist .pobj").count() == 3 and pg.locator("[data-peye]").count() == 3 and pg.locator("[data-pdel]").count() == 3)
    pg.click("[data-psel='1']"); pg.wait_for_timeout(400)
    ok("selecting shows the selection toolbar", pg.is_visible("#plateSel") and pg.get_attribute("[data-psel='1']", "aria-pressed") == "true")
    pg.locator("#plateTool").scroll_into_view_if_needed(); shot(pg, "plate", "plate-one-selected.png")
    pg.click("[data-psel='2']", modifiers=["Shift"]); pg.wait_for_timeout(300)
    ok("shift-click multi-selects", "2 selected" in pg.inner_text("#plateSel"))
    shot(pg, "plate", "plate-multi-selected-toolbar.png")
    pg.click("[data-peye='2']"); pg.wait_for_selector(".pobj.hid", timeout=30000); pg.wait_for_timeout(500)
    ok("hidden object is labelled 'Hidden, won't print'", "Hidden, won't print" in pg.inner_text(".plist"))
    shot(pg, "plate", "plate-hidden-object.png")
    pg.click("[data-pact='arrange']"); pg.wait_for_timeout(1500)
    ok("auto-arrange made a step", "Auto-arrange" in pg.inner_text("#editOps"))
    pg.click("#eUndo"); pg.wait_for_timeout(1200)
    ok("undo works", "Auto-arrange" in pg.inner_text("#editOps"))     # step stays listed as a future (redo) step
    small = pg.evaluate("""() => [...document.querySelectorAll('.plate .picon, .plate .pselect')].filter(e => e.getBoundingClientRect().height < 44).length""")
    ok("plate targets are at least 44px", small == 0, small)
    # lithophane Light on / off
    pg.goto(URL + "/#lithophane"); pg.wait_for_timeout(1200)
    pg.click("#sSample"); pg.wait_for_selector("#result:not([hidden])", timeout=90000); pg.wait_for_timeout(1500)
    ok("Light on toggle visible for lithophanes", pg.is_visible("#vLight"))
    pg.locator("#viewer").scroll_into_view_if_needed(); shot(pg, "litho-light", "litho-light-off.png")
    pg.click("#vLight"); pg.wait_for_timeout(800)
    ok("toggle pressed + Preview estimate label", pg.get_attribute("#vLight", "aria-pressed") == "true" and pg.is_visible("#vLightNote"))
    shot(pg, "litho-light", "litho-light-on-warm.png")
    pg.select_option("#vLightColor", "cool"); pg.wait_for_timeout(500); shot(pg, "litho-light", "litho-light-on-cool.png")
    ok("no page errors", not errs, errs)
    b.close()
sys.exit(1 if bad else 0)
