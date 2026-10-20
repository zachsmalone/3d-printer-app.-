"""TorchC0 tab in a real browser (Chrome + WebKit): open /#torchc0, inputs are visible and clickable, pick a file,
Prepare for resin, see the estimate and STL/3MF links. python tests/ui_torchc0.py URL"""
import os, shutil, sys, tempfile
import trimesh
from playwright.sync_api import sync_playwright
URL = sys.argv[1].rstrip("/"); bad = []


def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c: bad.append(n)


def run(name, launch, stl):
    b = launch(); pg = b.new_page(viewport={"width": 1280, "height": 900})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL + "/#torchc0"); pg.wait_for_selector("#rzGo", timeout=20000)
    for sel in ("#rzPrinter", "#rzFile", "#rzLayer", "#rzHollow", "#rzSup"):
        box = pg.locator(sel).bounding_box()
        ok(f"{name}: {sel} visible and sized", pg.is_visible(sel) and box and box["width"] > 8 and box["height"] > 8, box)
    pg.click("#rzHollow"); ok(f"{name}: hollow checkbox clickable", not pg.is_checked("#rzHollow"))
    pg.fill("#rzLayer", "0.05"); ok(f"{name}: layer field editable", pg.input_value("#rzLayer") == "0.05")
    pg.set_input_files("#rzFile", stl)
    pg.click("#rzGo")
    pg.wait_for_selector("#torchOut a[href$='torchc0.stl']", timeout=200000)
    txt = pg.inner_text("#torchOut")
    ok(f"{name}: estimate shown", "ml" in txt and "layers" in txt, txt)
    ok(f"{name}: 3MF link", pg.locator("#torchOut a[href$='torchc0.3mf']").count() == 1)
    ok(f"{name}: no page errors", not errs, errs)
    b.close()
    if not bad: print(f"PASS {name}")


d = tempfile.mkdtemp(prefix="zeim-torchc0-")
try:
    stl = os.path.join(d, "cube.stl"); trimesh.creation.box([20, 15, 10]).export(stl)
    with sync_playwright() as p:
        run("chrome", lambda: p.chromium.launch(), stl)
        run("webkit", lambda: p.webkit.launch(), stl)
finally:
    shutil.rmtree(d, ignore_errors=True)
sys.exit(1 if bad else 0)
