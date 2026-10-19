"""B13: tapping/clicking an edge in the CAD workspace shows its length in mm (on the model and in the polite live hint),
both in direct modelling and in Measure mode; two-point measuring still works.   python tests/ui_cadws_edge_len.py URL"""
import os, sys, tempfile, time
import trimesh
from playwright.sync_api import sync_playwright

URL = sys.argv[1].rstrip("/")
bad = []


def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c:
        bad.append(n)


def wait(pg, js, timeout=60000):
    t = time.time()
    while time.time() - t < timeout / 1000:
        try:
            if pg.evaluate(js):
                return True
        except Exception:
            pass
        pg.wait_for_timeout(250)
    raise TimeoutError(js)


def scr(pg, v):
    return pg.evaluate("""(v) => { const c = document.querySelector('#cwStage canvas'), r = c.getBoundingClientRect();
      const p = new window.__cad.V3(...v).project(window.__cad.cam); return [r.left + (p.x + 1) / 2 * r.width, r.top + (1 - p.y) / 2 * r.height]; }""", v)


d = tempfile.mkdtemp(); stl = os.path.join(d, "block.stl")
m = trimesh.creation.box((40, 30, 10)); m.apply_translation((0, 0, 5)); m.export(stl)     # front top edge: y=-15, z=10, 40 mm long
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("CHROME") or None, args=["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"])
    for tag, vw, vh, touch in (("chrome", 1440, 900, False), ("chrome ipad-touch", 1024, 768, True)):
        pg = b.new_context(viewport={"width": vw, "height": vh}, has_touch=touch).new_page()
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        tap = (lambda x, y: pg.touchscreen.tap(x, y)) if touch else (lambda x, y: pg.mouse.click(x, y))
        pg.goto(URL + "/static/cad.html"); pg.wait_for_timeout(800)
        pg.set_input_files("#cwFile", stl)
        wait(pg, "() => window.__cad.S.scene && window.__cad.S.scene.bodies.length === 1")
        pg.evaluate("window.__cad.viewAlong(new window.__cad.V3(0.9,-1.3,1))"); pg.wait_for_timeout(400)
        hint = lambda: pg.inner_text("#cwHint")
        meas = lambda: [e.inner_text() for e in pg.query_selector_all(".cw-meas")]
        ok(f"{tag}: the hint that carries the readout is a polite live region",
           pg.get_attribute("#cwHint", "aria-live") == "polite" and pg.get_attribute("#cwHint", "role") == "status")
        tap(*scr(pg, [0, -15, 10])); pg.wait_for_timeout(400)
        ok(f"{tag}: tapping an edge selects it with the edge actions", pg.locator(".cw-ctx [data-c=fi]").count() == 1)
        ok(f"{tag}: the picked edge shows its length on the model", meas() == ["40 mm"], meas())
        ok(f"{tag}: and the live hint announces it", "40 mm" in hint(), hint())
        tap(*scr(pg, [5, 3, 10])); pg.wait_for_timeout(400)
        ok(f"{tag}: tapping a face instead drops the edge length", pg.locator(".cw-ctx [data-c=pp]").count() == 1 and not meas(), meas())
        pg.keyboard.press("Escape"); pg.click("#cwMeasure"); pg.wait_for_timeout(200)
        ok(f"{tag}: Measure is on", pg.evaluate("window.__cad.S.measure"))
        tap(*scr(pg, [0, -15, 10])); pg.wait_for_timeout(400)
        ok(f"{tag}: Measure mode: tapping an edge measures the whole edge", pg.evaluate("window.__cad.S.measPts.length") == 2 and meas() and meas()[0].startswith("40 mm"), meas())
        ok(f"{tag}: Measure mode: the result is announced in the live hint", "40 mm" in hint(), hint())
        pg.click("#cwDesel"); pg.wait_for_timeout(200)
        tap(*scr(pg, [-10, 0, 10])); pg.wait_for_timeout(300); tap(*scr(pg, [10, 0, 10])); pg.wait_for_timeout(400)
        ok(f"{tag}: two points on a face still measure point to point", meas() and meas()[0].startswith("20 mm") and "20 mm" in hint(), (meas(), hint()))
        ok(f"{tag}: no JS errors", not errs, errs[:3])
    b.close()
print("ALL PASS" if not bad else f"{len(bad)} FAIL"); sys.exit(1 if bad else 0)
