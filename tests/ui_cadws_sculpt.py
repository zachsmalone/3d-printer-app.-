"""Sculpt in the CAD workspace: import a sphere, draw strokes with the mouse (and X symmetry), grab, undo.
python tests/ui_cadws_sculpt.py URL OUTDIR"""
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


d = tempfile.mkdtemp(); stl = os.path.join(d, "head.stl")
m = trimesh.creation.icosphere(subdivisions=5, radius=25); m.apply_translation((0, 0, 25)); m.export(stl)
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("CHROME") or None, args=["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"])
    pg = b.new_context(viewport={"width": 1440, "height": 900}).new_page()
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL + "/static/cad.html"); pg.wait_for_timeout(800)
    pg.set_input_files("#cwFile", stl)
    wait(pg, "() => window.__cad.S.scene && window.__cad.S.scene.bodies.length === 1")
    pg.evaluate("window.__cad.viewAlong(new window.__cad.V3(0.3,-1,0.6))"); pg.wait_for_timeout(400)
    pg.keyboard.press("u"); pg.wait_for_timeout(300)
    ok("sculpt panel with 7 brushes", pg.locator("#tBrush button").count() == 7)
    pg.check("#tSym"); pg.fill("#tRad", "6"); pg.dispatch_event("#tRad", "input")
    a, z = scr(pg, [8, -22, 35]), scr(pg, [16, -18, 25])
    pg.mouse.move(*a); pg.mouse.down()
    for k in range(1, 13):
        pg.mouse.move(a[0] + (z[0] - a[0]) * k / 12, a[1] + (z[1] - a[1]) * k / 12); pg.wait_for_timeout(20)
    pg.mouse.up()
    wait(pg, "() => window.__cad.S.scene.ops.length === 1")
    lab = pg.evaluate("window.__cad.S.scene.ops[0].label")
    ok("a mouse stroke became a History step with mirror", lab.startswith("Sculpt Draw") and "mirror" in lab, lab)
    pg.click("#tBrush [data-v=grab]")
    g = scr(pg, [0, -25, 25]); pg.mouse.move(*g); pg.mouse.down(); pg.mouse.move(g[0], g[1] + 60, steps=8); pg.mouse.up()
    wait(pg, "() => window.__cad.S.scene.ops.length === 2")
    ok("grab stroke recorded", "Grab" in pg.evaluate("window.__cad.S.scene.ops[1].label"))
    pg.wait_for_timeout(500)
    pg.mouse.move(*scr(pg, [-10, -22, 30])); pg.wait_for_timeout(200)
    pg.screenshot(path=f"{OUT}/sculpt-mode.png")
    pg.keyboard.press("Control+z"); wait(pg, "() => window.__cad.S.scene.head === 1")
    ok("undo removes the last stroke", True)
    ok("no JS errors", not errs, errs[:3])
    b.close()
print("ALL PASS" if not bad else f"{len(bad)} FAIL"); sys.exit(1 if bad else 0)
