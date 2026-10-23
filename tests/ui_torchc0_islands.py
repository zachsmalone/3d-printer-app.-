"""TorchC0 islands / suction cups / cost in Chromium at desktop, 390 and 320 px: markers in the 3D view, counts,
one-click 'Add supports to islands' and 'Add drain hole', dismissible warnings, cost only once a price is typed,
44 px taps and no sideways scroll. python tests/ui_torchc0_islands.py URL"""
import os, shutil, sys, tempfile
import trimesh
from playwright.sync_api import sync_playwright
URL = sys.argv[1].rstrip("/"); bad = []


def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c: bad.append(n)


def box(e, a):
    return trimesh.creation.box(extents=e).apply_translation(a)


def show_go(pg):
    # On phones the floating "Resin settings" panel starts as a chip once a result is showing: one tap opens it
    pg.wait_for_selector("#rzGo", state="attached", timeout=20000)
    chip = pg.locator(".zws-p.min:has(#rzGo) .zws-chip")
    if chip.count(): chip.first.click()
    pg.wait_for_selector("#rzGo", timeout=20000)


def prep(pg, stl, price=""):
    pg.goto(URL + "/#torchc0"); show_go(pg)
    pg.evaluate("localStorage.removeItem('zeim.resinPrice')")
    pg.reload(); show_go(pg)
    pg.evaluate("document.querySelector('#rzAdv').open = true")   # S9: expert settings live behind Advanced
    for sel, v in (("#rzTilt", "0"), ("#rzLayer", "0.1")):
        pg.fill(sel, v)
    if pg.is_checked("#rzHollow"): pg.click("#rzHollow")
    if pg.is_checked("#rzSup"): pg.click("#rzSup")
    pg.fill("#rzCost", price)
    pg.set_input_files("#rzFile", stl); pg.click("#rzGo")
    pg.wait_for_selector("#torchOut a[href$='torchc0.stl']", timeout=200000)


def again(pg, btn):
    old = pg.get_attribute("#torchOut a[href$='torchc0.stl']", "href")
    pg.click(btn)
    pg.wait_for_function("o => { const a = document.querySelector(\"#torchOut a[href$='torchc0.stl']\"); return a && a.getAttribute('href') !== o; }", arg=old, timeout=200000)


def run(name, w, h, d):
    b = sync_playwright_ctx.chromium.launch(); pg = b.new_page(viewport={"width": w, "height": h})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    isl = os.path.join(d, "island.stl"); trimesh.util.concatenate([box([10, 10, 10], [0, 0, 5]), box([5, 5, 2], [20, 0, 6])]).export(isl)
    prep(pg, isl)
    ok(f"{name}: island count", "1 island" in pg.inner_text("#rzIslands"), pg.inner_text("#torchOut"))
    pg.wait_for_function("document.querySelector('#rzView')?.dataset.markers", timeout=20000)
    ok(f"{name}: island marker in 3D view", pg.get_attribute("#rzView", "data-markers") == "1" and pg.locator("#rzView canvas").count() == 1)
    ok(f"{name}: no cost without a price", "enter a price" in pg.inner_text("#rzCostOut"))
    bb = pg.locator("#rzFixIsl").bounding_box()
    ok(f"{name}: fix button 44px", bb and bb["height"] >= 44, bb)
    ok(f"{name}: no sideways scroll", pg.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), pg.evaluate("document.documentElement.scrollWidth"))
    again(pg, "#rzFixIsl")
    ok(f"{name}: islands supported", "0 islands" in pg.inner_text("#rzIslands"), pg.inner_text("#rzIslands"))
    cup = os.path.join(d, "cup.stl")
    trimesh.boolean.difference([box([20, 20, 10], [0, 0, 5]), box([14, 14, 8], [0, 0, 3.9])], engine="manifold").export(cup)
    prep(pg, cup, "40")
    ok(f"{name}: suction count", "1 suction cup" in pg.inner_text("#rzCups"), pg.inner_text("#torchOut"))
    ok(f"{name}: cost with typed price, labelled estimate", "$" in pg.inner_text("#rzCostOut") and "estimate" in pg.inner_text("#rzCostOut"), pg.inner_text("#rzCostOut"))
    pg.click("#rzCups .rzDismiss"); ok(f"{name}: suction warning dismissible", pg.locator("#rzCups").count() == 0)
    ok(f"{name}: downloads still there", pg.locator("#torchOut a[href$='torchc0.3mf']").count() == 1)
    prep(pg, cup, "40"); again(pg, "#rzFixCup")
    ok(f"{name}: drain hole added", "0 suction cups" in pg.inner_text("#rzCups"), pg.inner_text("#torchOut"))
    ok(f"{name}: no page errors", not errs, errs)
    pg.screenshot(path=os.path.join(tempfile.gettempdir(), f"torchc0_islands_{w}.png"), full_page=True)
    b.close()


d = tempfile.mkdtemp(prefix="zeim-torchc0i-")
try:
    with sync_playwright() as sync_playwright_ctx:
        for w, h in ((1280, 900), (390, 844), (320, 640)):
            run(f"chrome {w}", w, h, d)
finally:
    shutil.rmtree(d, ignore_errors=True)
if not bad: print("PASS chrome")
sys.exit(1 if bad else 0)
