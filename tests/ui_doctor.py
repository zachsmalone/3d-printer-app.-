"""Failure photo doctor in a real browser (Chrome + WebKit), phone width: pick Stringing, add a photo (permission box),
get plain fixes with PrusaSlicer keys, 'Use in my next slice' asks first (Cancel changes nothing, Yes saves it), then the
Slicer panel shows the change with Undo. python tests/ui_doctor.py URL"""
import io, os, shutil, sys, tempfile
import trimesh
from PIL import Image
from playwright.sync_api import sync_playwright
URL = sys.argv[1].rstrip("/"); bad = []


def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c: bad.append(n)


def run(name, launch, png, stl):
    b = launch(); ctx = b.new_context(viewport={"width": 390, "height": 844}); pg = ctx.new_page()
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL + "/#smartfix"); pg.wait_for_timeout(800)
    pg.click("#docOpen")
    pg.wait_for_selector("#docSyms input[value=stringing]", timeout=20000)
    ok(f"{name}: 25 problems to pick", pg.locator("#docSyms input").count() == 25)
    pg.check("#docSyms input[value=stringing]")
    pg.set_input_files("#docPhoto", png)
    try:                                    # the preview appears after the browser reads the file; don't race it under load
        pg.wait_for_selector("#docPrev", state="visible", timeout=10000); pg.wait_for_selector("#docAck", state="visible", timeout=10000)
    except Exception:
        pass
    ok(f"{name}: photo preview + permission box", pg.is_visible("#docPrev") and pg.is_visible("#docAck"))
    pg.check("#docAck")
    pg.click("#docGo")
    pg.wait_for_selector("#docOut .docfix, #docOut [role=alert]", timeout=30000)
    t = pg.inner_text("#docOut")
    ok(f"{name}: plain fixes with PrusaSlicer keys", "Stringing" in t and "Lower nozzle temperature" in t and "PrusaSlicer: retract_length" in t, t)
    ok(f"{name}: says the photo isn't read or kept", "doesn't read photos" in t and "not kept" in t, t)
    btn = pg.locator("#docOut [data-apply]").first
    ok(f"{name}: offer shows before -> after", "210 → 205" in btn.inner_text(), btn.inner_text())
    btn.click(); pg.wait_for_selector("#dlgConfirm[open]", timeout=5000)
    ok(f"{name}: asks first", "210" in pg.inner_text("#confirmMsg") and "205" in pg.inner_text("#confirmMsg"))
    pg.keyboard.press("Escape"); pg.wait_for_timeout(300)
    ok(f"{name}: cancel changes nothing", pg.evaluate("sessionStorage.getItem('zeim.smartfix.apply')") is None)
    btn.click(); pg.wait_for_selector("#dlgConfirm[open]", timeout=5000); pg.click("#confirmOk"); pg.wait_for_timeout(300)
    ok(f"{name}: yes saves it for the next slice", "spNozT" in (pg.evaluate("sessionStorage.getItem('zeim.smartfix.apply')") or ""))
    pg.goto(URL + "/#edit"); pg.wait_for_timeout(800)
    pg.set_input_files("#editFile", stl)
    pg.wait_for_selector("#spSmartFix", timeout=60000)
    ok(f"{name}: slicer shows the change", pg.input_value("#spNozT") == "205" and "nozzle temperature 205" in pg.inner_text("#spSmartFix"), pg.input_value("#spNozT"))
    pg.click("#spSmartUndo")
    ok(f"{name}: undo puts it back", pg.input_value("#spNozT") == "210" and pg.locator("#spSmartFix").count() == 0, pg.input_value("#spNozT"))
    ok(f"{name}: no page errors", not errs, errs)
    b.close()
    if not bad: print(f"PASS {name}")


d = tempfile.mkdtemp(prefix="zeim-doctor-")
try:
    png = os.path.join(d, "fail.png"); Image.new("RGB", (80, 60), (180, 60, 40)).save(png)
    stl = os.path.join(d, "cube.stl"); trimesh.creation.box([20, 20, 10]).export(stl)
    with sync_playwright() as p:
        run("chrome", lambda: p.chromium.launch(), png, stl)
        run("webkit", lambda: p.webkit.launch(), png, stl)
finally:
    shutil.rmtree(d, ignore_errors=True)
sys.exit(1 if bad else 0)
