"""Layer-by-layer preview in a real browser (Chrome + WebKit): slice the sample in the Slicer tab path, open the preview,
the slider and buttons move between layers, the canvas draws coloured lines, the legend lists line kinds.
python tests/ui_layers.py URL"""
import os, shutil, sys, tempfile
import trimesh
from playwright.sync_api import sync_playwright
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__))); import zws_open; zws_open.install()   # C: phone panels start as chips
URL = sys.argv[1].rstrip("/"); bad = []
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c: bad.append(n)


def wait(pg, js, timeout=60000):
    import time
    end = time.time() + timeout / 1000
    while time.time() < end:
        if pg.evaluate(f"() => !!({js})"):
            return True
        pg.wait_for_timeout(250)
    return False


def run(name, launch, stl):
    b = launch(); ctx = b.new_context(viewport={"width": 390, "height": 844}); pg = ctx.new_page()
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    # the 2D layer view is now the fallback when WebGL is off (the 3D G-code preview is covered by ui_gcode_preview.py)
    pg.add_init_script("(() => { const g = HTMLCanvasElement.prototype.getContext; HTMLCanvasElement.prototype.getContext = function (t, ...a) { return /webgl/.test(t) ? null : g.call(this, t, ...a); }; })()")
    pg.goto(URL + "/#edit"); pg.wait_for_timeout(1000)
    pg.set_input_files("#editFile", stl)
    pg.wait_for_selector("#editResult:not([hidden])", timeout=60000)
    pg.wait_for_selector("#spGo", timeout=30000)
    pg.click("#spGo")
    pg.wait_for_selector("#spOut .slicestats, #spOut [role=alert]", timeout=120000)
    ok(f"{name}: slice finished with a layer preview button", pg.locator("#spOut #lpOpen").count() == 1, pg.inner_text("#spOut"))
    pg.click("#lpOpen")
    ok(f"{name}: preview opens", wait(pg, "!document.querySelector('#lpBox').hidden && /Layer \\d+ of \\d+/.test(document.querySelector('#lpInfo').textContent)"), pg.inner_text("#lpInfo"))
    n = int(pg.get_attribute("#lpRange", "max"))
    ok(f"{name}: many layers", n > 20, n)
    ok(f"{name}: starts on the top layer", f"Layer {n} of {n}" in pg.inner_text("#lpInfo"), pg.inner_text("#lpInfo"))
    pg.click("#lpPrev")
    ok(f"{name}: Previous goes down one layer", f"Layer {n - 1} of {n}" in pg.inner_text("#lpInfo"), pg.inner_text("#lpInfo"))
    pg.focus("#lpRange"); pg.keyboard.press("Home")
    ok(f"{name}: keyboard Home on the slider shows layer 1 at 0.20 mm", "Layer 1 of" in pg.inner_text("#lpInfo") and "0.20 mm" in pg.inner_text("#lpInfo"), pg.inner_text("#lpInfo"))
    pg.click("#lpNext")
    ok(f"{name}: Next goes up one layer", "Layer 2 of" in pg.inner_text("#lpInfo"))
    lit = pg.evaluate("""(() => { const c = document.querySelector('#lpCanvas'), x = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
        let n = 0; for (let i = 0; i < x.length; i += 4) if (x[i] > 120 || x[i + 1] > 120) n++; return n; })()""")
    ok(f"{name}: canvas draws the layer's lines", lit > 200, lit)
    ok(f"{name}: legend names the line kinds", "Outer wall" in pg.inner_text("#lpLegend"), pg.inner_text("#lpLegend"))
    ok(f"{name}: slider has a label and value text", pg.locator("label[for=lpRange]").count() == 1 and "Layer 2" in (pg.get_attribute("#lpRange", "aria-valuetext") or ""))
    sz = pg.evaluate("[...document.querySelectorAll('#lpBox button')].map(b => { const r = b.getBoundingClientRect(); return Math.min(r.width, r.height); })")
    ok(f"{name}: buttons are 44 px targets", all(v >= 44 for v in sz), sz)
    ok(f"{name}: no page errors", not errs, errs)
    b.close()
    if not bad: print(f"PASS {name}")


d = tempfile.mkdtemp(prefix="zeim-layers-")
try:
    stl = os.path.join(d, "cube.stl"); trimesh.creation.box([20, 20, 10]).export(stl)
    with sync_playwright() as p:
        run("chrome", lambda: p.chromium.launch(), stl)
        run("webkit", lambda: p.webkit.launch(), stl)
finally:
    shutil.rmtree(d, ignore_errors=True)
sys.exit(1 if bad else 0)
