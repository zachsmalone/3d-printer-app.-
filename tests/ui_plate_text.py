"""Plate editor text tool in a real browser (Chrome + WebKit), phone width: select one object, Add text -> Raised "HI"
on top makes one step and the object 1 mm taller; a blocked word is refused in plain words; Undo removes the text.
python tests/ui_plate_text.py URL"""
import os, shutil, sys, tempfile
import trimesh
from playwright.sync_api import sync_playwright
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__))); import zws_open; zws_open.install(("tools",))   # C: phone panels start as chips; open Tools only (two open panels crowd a phone)
URL = sys.argv[1].rstrip("/"); bad = []


def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c: bad.append(n)


def wait_text(pg, sel, want, secs=60):
    for _ in range(secs * 5):
        if pg.locator(sel).count() and want in pg.inner_text(sel):
            return True
        pg.wait_for_timeout(200)
    return False


def run(name, launch, files):
    b = launch(); ctx = b.new_context(viewport={"width": 390, "height": 844}); pg = ctx.new_page()
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    nb = len(bad)
    pg.goto(URL + "/#slicer"); pg.wait_for_timeout(1000)
    pg.set_input_files("#editFile", files)
    pg.click("#multiPlate"); pg.wait_for_selector("#plateTool", timeout=60000); pg.wait_for_timeout(600)
    ok(f"{name}: no text tool until one object is selected", pg.locator("#pText").count() == 0)
    pg.click("[data-psel='0']"); pg.wait_for_selector("#pText", timeout=5000)
    pg.click("#pText summary")
    ok(f"{name}: plain words + checked like other words + undo", all(w in pg.inner_text("#pTextHelp") for w in ("flat side", "checked like any other words", "Undo removes it")))
    small = pg.evaluate("""() => [...document.querySelectorAll('#pText > summary, #pText select, #pText button, #pText .seg-radio label')].filter(e => e.getBoundingClientRect().height < 44).length""")
    ok(f"{name}: text controls are at least 44px", small == 0, small)
    pg.fill("#pTxt", "sh1t"); pg.click("#pTextGo"); pg.wait_for_timeout(1500)
    ok(f"{name}: blocked word refused, no step", "Plate: Raised" not in pg.inner_text("#editOps"))
    pg.click("[data-psel='0']") if pg.locator("#pText").count() == 0 else None
    if not pg.locator("#pText[open]").count():
        pg.click("#pText summary")
    pg.fill("#pTxt", "HI"); pg.fill("#pTxtH", "8"); pg.fill("#pTxtD", "1"); pg.check("#pText input[name=mode][value=emboss]")
    pg.click("#pTextGo")
    ok(f"{name}: one step in the list", wait_text(pg, "#editOps", "Plate: Raised text “HI”"), pg.inner_text("#editOps"))
    ok(f"{name}: object is 1 mm taller", wait_text(pg, ".plist", "30 × 30 × 31 mm"), pg.inner_text(".plist"))
    pg.click("#eUndo")
    ok(f"{name}: undo removes the text", wait_text(pg, "[data-psel='0']", "30 × 30 × 30 mm"), pg.inner_text(".plist"))
    ok(f"{name}: no page errors", not errs, errs)
    b.close()
    if len(bad) == nb: print(f"PASS {name}")


d = tempfile.mkdtemp(prefix="zeim-ptext-")
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
