"""Print cost estimate in a real browser (Chrome + WebKit), phone width: slice a cube, the box shows grams + time from
the G-code, typing a price per kg shows 'About $x of filament' = grams x price / 1000, labelled an estimate; the price
is remembered in this browser for the next slice. python tests/ui_cost.py URL"""
import os, re, shutil, sys, tempfile
import trimesh
from playwright.sync_api import sync_playwright
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__))); import zws_open; zws_open.install()   # C: phone panels start as chips
URL = sys.argv[1].rstrip("/"); bad = []


def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c: bad.append(n)


def slice_once(pg):
    pg.wait_for_selector("#spGo", timeout=30000)
    pg.click("#spGo")
    pg.wait_for_selector("#spOut .slicestats, #spOut [role=alert]", timeout=120000)


def run(name, launch, stl):
    b = launch(); ctx = b.new_context(viewport={"width": 390, "height": 844}); pg = ctx.new_page()
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    nb = len(bad)
    pg.goto(URL + "/#edit"); pg.wait_for_timeout(1000)
    pg.set_input_files("#editFile", stl)
    pg.wait_for_selector("#editResult:not([hidden])", timeout=60000)
    slice_once(pg)
    ok(f"{name}: cost box under the slice", pg.locator("#costBox").count() == 1, pg.inner_text("#spOut"))
    grams = float(pg.get_attribute("#costBox", "data-grams"))
    t = pg.inner_text("#costBox")
    ok(f"{name}: grams + time from the G-code, labelled an estimate", f"{grams:g} g" in t and "min" in t and "Estimate" in t, t)
    ok(f"{name}: asks for a price first", "Type your price per kg" in pg.inner_text("#costOut"))
    pg.fill("#costKg", "25"); pg.wait_for_timeout(200)
    c = grams / 1000 * 25
    want = f"${c:.2f}" if c >= 0.005 else "under $0.01"                    # money is always 2 decimals
    out = pg.inner_text("#costOut")
    ok(f"{name}: cost = grams x price", f"About {want} of filament" in out and "Estimate only" in out, (want, out))
    pg.select_option("#costCur", "€"); pg.wait_for_timeout(200)
    ok(f"{name}: currency switch", "€" in pg.inner_text("#costOut"), pg.inner_text("#costOut"))
    ok(f"{name}: says what it leaves out", "leaves out power, failed prints" in pg.inner_text("#costBox"))
    small = pg.evaluate("""() => [...document.querySelectorAll('#costBox select, #costBox input')].filter(e => e.getBoundingClientRect().height < 44).length""")
    ok(f"{name}: inputs are 44px", small == 0, small)
    ok(f"{name}: has a label", pg.locator("label[for=costKg]").count() == 1)
    slice_once(pg)
    ok(f"{name}: price remembered for the next slice", pg.input_value("#costKg") == "25" and "€" in pg.inner_text("#costOut"), pg.input_value("#costKg"))
    ok(f"{name}: no page errors", not errs, errs)
    b.close()
    if len(bad) == nb: print(f"PASS {name}")


d = tempfile.mkdtemp(prefix="zeim-cost-")
try:
    stl = os.path.join(d, "cube.stl"); trimesh.creation.box([20, 20, 10]).export(stl)
    with sync_playwright() as p:
        run("chrome", lambda: p.chromium.launch(), stl)
        run("webkit", lambda: p.webkit.launch(), stl)
finally:
    shutil.rmtree(d, ignore_errors=True)
sys.exit(1 if bad else 0)
