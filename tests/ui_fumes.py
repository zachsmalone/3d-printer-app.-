"""E1: picking ABS / ASA / PC in the slicer panel shows a ventilation + enclosure warning at once; pressing Slice asks first
(role=alert, focus on the confirm button) and slices only after "I have good ventilation". Temps are capped to the printer.
Chrome + WebKit, 390 px.   python tests/ui_fumes.py URL  (TEMP-data server)"""
import json, os, shutil, sys, tempfile
import trimesh
from playwright.sync_api import sync_playwright
URL = sys.argv[1].rstrip("/"); bad = []
AXE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "axe.min.js")


def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c: bad.append(n)


def run(name, launch, stl, with_axe):
    try: b = launch()
    except Exception as e: print(f"SKIP {name}: {str(e).splitlines()[0][:80]}"); return
    n0 = len(bad)
    pg = b.new_context(viewport={"width": 390, "height": 844}, bypass_csp=True).new_page()
    pg.goto(URL + "/#edit"); pg.wait_for_timeout(1000)
    pg.set_input_files("#editFile", stl)
    pg.wait_for_selector("#editResult:not([hidden])", timeout=60000)
    pg.wait_for_selector("#spMat", timeout=30000)
    ok(f"{name}: PLA shows no fume warning", pg.inner_text("#spMatWarn").strip() == "")
    pg.select_option("#spMat", "ABS"); pg.wait_for_timeout(150)
    w = pg.inner_text("#spMatWarn")
    ok(f"{name}: picking ABS shows the ventilation + enclosure warning at once", "needs fresh air and an enclosure" in w and "well-ventilated" in w and "not test-printed" in w, w)
    pg.select_option("#spMat", "ASA"); pg.wait_for_timeout(100)
    ok(f"{name}: ASA bed temp starts capped at the K1's 100 °C", pg.input_value("#spBedT") == "100", pg.input_value("#spBedT"))
    pg.select_option("#spMat", "ABS")
    pg.click("#spGo")
    pg.wait_for_selector("#spOut [role=alert] #spVentOk", timeout=30000)
    out = pg.inner_text("#spOut")
    ok(f"{name}: Slice asks first with the warning (nothing sliced yet)", "enclosure" in out and "I have good ventilation" in out and pg.locator("#spOut .slicestats").count() == 0, out)
    ok(f"{name}: focus moves to the confirm button, one copy of the warning on screen", pg.evaluate("document.activeElement.id") == "spVentOk" and pg.locator("#spMatWarn").is_hidden())
    if with_axe and os.path.exists(AXE):
        pg.add_script_tag(path=AXE)
        r = pg.evaluate("axe.run('#spOut', {runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}}).then(r=>r.violations.map(v=>({id:v.id,n:v.nodes.length})))")
        ok(f"{name}: axe clean on the warning", not r, json.dumps(r))
    pg.click("#spVentNo"); pg.wait_for_timeout(100)
    ok(f"{name}: 'Pick another material' clears it and focuses the material list", pg.inner_text("#spOut").strip() == "" and pg.evaluate("document.activeElement.id") == "spMat")
    pg.click("#spGo"); pg.wait_for_selector("#spVentOk", timeout=30000); pg.click("#spVentOk")
    pg.wait_for_selector("#spOut .slicestats, #spOut [role=alert]:not(:has(#spVentOk))", timeout=120000)
    res = pg.inner_text("#spOut")
    ok(f"{name}: after the confirm it slices, with an ABS reminder", pg.locator("#spOut .slicestats").count() == 1 and "ABS" in res and "ventilate" in res, res)
    b.close()
    if len(bad) == n0: print(f"PASS {name}")


d = tempfile.mkdtemp(prefix="zeim-fumes-")
try:
    stl = os.path.join(d, "cube.stl"); trimesh.creation.box([20, 20, 10]).export(stl)
    with sync_playwright() as p:
        run("chrome", lambda: p.chromium.launch(), stl, True)
        run("webkit", lambda: p.webkit.launch(), stl, False)
finally:
    shutil.rmtree(d, ignore_errors=True)
sys.exit(1 if bad else 0)
