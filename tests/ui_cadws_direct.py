"""Direct modelling in the CAD workspace: tap a face -> floating actions + drag the push/pull arrow; tap an edge -> fillet.
python tests/ui_cadws_direct.py URL OUTDIR"""
import os, sys, tempfile, time
import trimesh
from playwright.sync_api import sync_playwright

URL, OUT = sys.argv[1].rstrip("/"), sys.argv[2]
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
m = trimesh.creation.box((40, 30, 10)); m.apply_translation((0, 0, 5)); m.export(stl)
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("CHROME") or None, args=["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"])
    for tag, vw, vh, touch in (("desktop", 1440, 900, False), ("ipad", 1024, 768, True)):
        pg = b.new_context(viewport={"width": vw, "height": vh}, has_touch=touch).new_page()
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(URL + "/static/cad.html"); pg.wait_for_timeout(800)
        pg.set_input_files("#cwFile", stl)
        wait(pg, "() => window.__cad.S.scene && window.__cad.S.scene.bodies.length === 1")
        pg.evaluate("window.__cad.viewAlong(new window.__cad.V3(0.9,-1.3,1))"); pg.wait_for_timeout(400)
        pg.mouse.click(*scr(pg, [5, 3, 10])); pg.wait_for_timeout(300)
        ok(f"{tag}: tapping a face pops up the action bar", pg.locator(".cw-ctx [data-c=pp]").count() == 1)
        hb = pg.locator(".cw-handle").bounding_box()
        pg.mouse.move(hb["x"] + 22, hb["y"] + 22); pg.mouse.down()
        pg.mouse.move(hb["x"] + 22, hb["y"] - 40, steps=6); pg.wait_for_timeout(200)
        live = pg.input_value("#ctxD")
        pg.screenshot(path=f"{OUT}/direct-pushpull{'' if tag == 'desktop' else '-ipad'}.png")
        pg.mouse.up()
        wait(pg, "() => window.__cad.S.scene.ops.length === 1")
        z = pg.evaluate("window.__cad.S.scene.analysis.size_mm[2]")
        ok(f"{tag}: dragging the arrow pulls the face (live readout {live} mm)", z > 10.5 and abs(z - 10 - float(live)) < 0.01, (z, live))
        pg.click("#cwHome"); pg.wait_for_timeout(600)
        pg.mouse.click(*scr(pg, [0, -15, z])); pg.wait_for_timeout(300)   # the front-right vertical edge
        if pg.locator(".cw-ctx [data-c=fi]").count():
            pg.fill("#ctxD", "3"); pg.click(".cw-ctx [data-c=fi]")
            wait(pg, "() => window.__cad.S.scene.ops.length === 2", 90000)
            ok(f"{tag}: tapping an edge -> Fillet adds a fillet step", "Fillet 3 mm (1 edges)" in pg.evaluate("window.__cad.S.scene.ops[1].label"))
        else:
            ok(f"{tag}: tapping an edge shows edge actions", False)
        pg.wait_for_timeout(500)
        pg.screenshot(path=f"{OUT}/direct-fillet{'' if tag == 'desktop' else '-ipad'}.png")
        ok(f"{tag}: no JS errors", not errs, errs[:3])
    b.close()
print("ALL PASS" if not bad else f"{len(bad)} FAIL"); sys.exit(1 if bad else 0)
