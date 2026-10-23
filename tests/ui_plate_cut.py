"""Plate editor cut tool in a real browser (Chrome + WebKit), phone width: select one object, open "Cut this object",
the red plane follows the slider, pick a magnet join (Simulated label), cut into 2 pieces as one step, Undo puts it back.
python tests/ui_plate_cut.py URL"""
import os, shutil, sys, tempfile
import trimesh
from playwright.sync_api import sync_playwright
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__))); import zws_open; zws_open.install(("tools",))   # C: phone panels start as chips; open Tools only (two open panels crowd a phone)
URL = sys.argv[1].rstrip("/"); bad = []


def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c: bad.append(n)


def wait_count(pg, n, secs=60):
    """Wait until the plate list shows n objects (the page's CSP forbids string evaluation, so poll)."""
    for _ in range(secs * 5):
        if pg.locator(".plist .pobj").count() == n:
            pg.wait_for_timeout(300); return
        pg.wait_for_timeout(200)


def run(name, launch, files):
    b = launch(); ctx = b.new_context(viewport={"width": 390, "height": 844}); pg = ctx.new_page()
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    nb = len(bad)
    pg.goto(URL + "/#slicer"); pg.wait_for_timeout(1000)
    pg.set_input_files("#editFile", files)
    pg.click("#multiPlate"); pg.wait_for_selector("#plateTool", timeout=60000); pg.wait_for_timeout(600)
    ok(f"{name}: two objects on the plate", pg.locator(".plist .pobj").count() == 2)
    ok(f"{name}: no cut tool until one object is selected", pg.locator("#pCut").count() == 0)
    pg.click("[data-psel='0']"); pg.wait_for_selector("#pCut", timeout=5000)
    pg.click("#pCut summary"); pg.wait_for_selector("#pCut[data-plane]", timeout=5000)
    ok(f"{name}: plane shown at the middle", pg.get_attribute("#pCut", "data-plane") == "z:15" and "Z = 15 mm" in pg.inner_text("#pCutPlane"), pg.get_attribute("#pCut", "data-plane"))
    pg.fill("#pCutAt", "10"); pg.dispatch_event("#pCutAt", "input"); pg.wait_for_timeout(200)
    ok(f"{name}: plane follows the number box", pg.get_attribute("#pCut", "data-plane") == "z:10" and pg.input_value("#pCutAtR") == "10", pg.get_attribute("#pCut", "data-plane"))
    pg.check("#pCut input[name=axis][value=x]"); pg.wait_for_timeout(300)
    ok(f"{name}: X cut resets to the middle + offers lay flat", pg.get_attribute("#pCut", "data-plane", timeout=3000).startswith("x:") and pg.is_visible("#pCutLay"))
    pg.check("#pCut input[name=axis][value=z]"); pg.wait_for_timeout(300)
    pg.fill("#pCutAt", "12"); pg.dispatch_event("#pCutAt", "input")
    pg.select_option("#pJoin", "magnet"); pg.wait_for_timeout(200)
    ok(f"{name}: magnet sizes + material appear", pg.is_visible("#pMagD") and pg.is_visible("#pCutMat") and not pg.is_visible("#pPinD"))
    ok(f"{name}: fit labelled Simulated, undo explained", "Simulated" in pg.inner_text("#pCutHelp") and "Undo puts the object back" in pg.inner_text("#pCutHelp"))
    small = pg.evaluate("""() => [...document.querySelectorAll('#pCut summary, #pCut select, #pCut button, #pCut .seg-radio label')].filter(e => e.getBoundingClientRect().height < 44).length""")
    ok(f"{name}: cut controls are at least 44px", small == 0, small)
    pg.click("#pCutGo")
    wait_count(pg, 3)
    ok(f"{name}: cut into 2 pieces (3 objects now)", pg.locator(".plist .pobj").count() == 3)
    note = pg.inner_text("#plateCutNote") if pg.locator("#plateCutNote").count() else ""
    ok(f"{name}: result says Simulated + test piece", "Simulated" in note and "test piece" in note, note)
    ok(f"{name}: one step in the list", "Plate: Cut Z at 12 mm (magnet)" in pg.inner_text("#editOps"), pg.inner_text("#editOps"))
    ok(f"{name}: no Fits-the-bed problems after the cut", "Overlaps" not in pg.inner_text(".plist") and "Hangs off" not in pg.inner_text(".plist"), pg.inner_text(".plist"))
    pg.click("#eUndo"); wait_count(pg, 2)
    ok(f"{name}: undo puts the object back", pg.locator(".plist .pobj").count() == 2)
    ok(f"{name}: no page errors", not errs, errs)
    b.close()
    if len(bad) == nb: print(f"PASS {name}")


d = tempfile.mkdtemp(prefix="zeim-cut-")
try:
    files = []
    for n, s in enumerate([(30, 30, 30), (20, 20, 30)]):
        f = os.path.join(d, f"part{n + 1}.stl"); trimesh.creation.box(s).export(f); files.append(f)
    with sync_playwright() as p:
        run("chrome", lambda: p.chromium.launch(), files)
        run("webkit", lambda: p.webkit.launch(), files)
finally:
    shutil.rmtree(d, ignore_errors=True)
sys.exit(1 if bad else 0)
