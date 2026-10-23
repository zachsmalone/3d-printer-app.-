"""Multi-object plate in a real browser (Chromium) at 390 and 320 px: upload 2 parts as one plate, select one, add 2
copies (auto-arranged), per-object duplicate + remove, spacing setting, 44px taps, overflow warning + split offer.
python tests/ui_multi_plate.py URL"""
import os, shutil, sys, tempfile
import trimesh
from playwright.sync_api import sync_playwright
URL = sys.argv[1].rstrip("/"); bad = []


def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c: bad.append(n)


def wait_count(pg, n, secs=60):
    for _ in range(secs * 5):
        if pg.locator(".plist .pobj").count() == n:
            pg.wait_for_timeout(300); return True
        pg.wait_for_timeout(200)
    return False


def run(width, files, bigfiles):
    name = f"chromium {width}px"
    with sync_playwright() as p:
        b = p.chromium.launch(); ctx = b.new_context(viewport={"width": width, "height": 800}, has_touch=True); pg = ctx.new_page()
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(URL + "/#slicer"); pg.wait_for_timeout(1000)
        pg.set_input_files("#editFile", files)
        pg.click("#multiPlate"); pg.wait_for_selector("#plateTool", timeout=60000); pg.wait_for_timeout(600)
        ok(f"{name}: two objects", pg.locator(".plist .pobj").count() == 2)
        ok(f"{name}: spacing defaults to 5 mm", pg.input_value("#pGap") == "5")
        ok(f"{name}: Add copies disabled until selection", pg.is_disabled("[data-pact=copies]"))
        pg.click("[data-psel='0']"); pg.wait_for_timeout(200)
        pg.fill("#pCopies", "2"); pg.dispatch_event("#pCopies", "input")
        pg.click("[data-pact=copies]")
        ok(f"{name}: 2 copies added (4 objects)", wait_count(pg, 4))
        pg.wait_for_timeout(1500)
        txt = pg.inner_text(".plist")
        ok(f"{name}: arranged, no overlaps / off-bed", "Overlaps" not in txt and "Hangs off" not in txt, txt)
        pg.click("[data-pdup='1']"); ok(f"{name}: per-object duplicate", wait_count(pg, 5))
        pg.click("[data-pdel='4']"); ok(f"{name}: per-object remove", wait_count(pg, 4))
        pg.fill("#pGap", "12"); pg.dispatch_event("#pGap", "input"); pg.click("[data-pact=arrange]"); pg.wait_for_timeout(1500)
        ok(f"{name}: arrange with 12 mm spacing reported", "12 mm apart" in pg.inner_text("#plateOut"), pg.inner_text("#plateOut"))
        small = pg.evaluate("""() => [...document.querySelectorAll('#plateTool .picon, #plateTool .pselect, #plateTool .tool-row .btn, #pGap, #pCopies, #plateTool .parr label')]
            .filter(e => e.offsetParent && e.getBoundingClientRect().height < 44).length""")
        ok(f"{name}: plate controls >= 44px tall", small == 0, small)
        wide = pg.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
        ok(f"{name}: no horizontal scroll", wide <= 1, wide)
        # overflow: 6 big parts on a 220 bed -> warning + split offer, never blocked
        pg.goto(URL + "/#slicer"); pg.wait_for_timeout(800)
        if pg.locator("#editClose").count(): pg.click("#editClose"); pg.wait_for_timeout(500)
        pg.set_input_files("#editFile", bigfiles)
        pg.click("#multiPlate"); pg.wait_for_selector("#plateTool", timeout=60000); pg.wait_for_timeout(600)
        pg.click("[data-pact=arrange]"); pg.wait_for_selector("#plateOverflow", timeout=30000)
        ok(f"{name}: overflow warning shown with split offer", pg.locator("#plateOverflow [data-pact=split]").count() == 1)
        pg.click("#plateOverflow [data-pact=split]")
        ok(f"{name}: split leaves the ones that fit", wait_count(pg, 4))
        pg.wait_for_timeout(1500)
        ok(f"{name}: link to plate 2", pg.locator("#plateOut a").count() == 1, pg.inner_text("#plateOut"))
        ok(f"{name}: no page errors", not errs, errs)
        b.close()


d = tempfile.mkdtemp(prefix="zeim-mp-")
try:
    files = []
    for n, s in enumerate([(30, 30, 20), (40, 20, 10)]):
        f = os.path.join(d, f"part{n + 1}.stl"); trimesh.creation.box(s).export(f); files.append(f)
    big = []
    for n in range(6):
        f = os.path.join(d, f"big{n + 1}.stl"); trimesh.creation.box((100, 100, 10)).export(f); big.append(f)
    for w in (390, 320):
        run(w, files, big)
finally:
    shutil.rmtree(d, ignore_errors=True)
print(f"{len(bad)} failed")
sys.exit(1 if bad else 0)
