"""Open a user's own STL in the CAD workspace (from the editor's 'Open in CAD' button and from CAD's Open menu),
then edit it: tap the top face, sketch a circle on it, cut it through, scale. python tests/ui_cadws_import.py URL OUTDIR"""
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


d = tempfile.mkdtemp()
stl = os.path.join(d, "my-bracket.stl")
m = trimesh.creation.box((60, 40, 12)); m.apply_translation((0, 0, 6)); m.export(stl)
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("CHROME") or None, args=["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"])
    for tag, vw, vh, touch in (("desktop", 1440, 900, False), ("ipad", 1024, 768, True)):
        pg = b.new_context(viewport={"width": vw, "height": vh}, has_touch=touch).new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        if tag == "desktop":      # path 1: the editor's upload -> "Open in CAD"
            pg.goto(URL + "/#edit"); pg.wait_for_timeout(1000)
            pg.set_input_files("#editFile", stl)
            pg.wait_for_selector("#editResult:not([hidden])", timeout=60000)
            href = pg.get_attribute("#editOpenCad", "href")
            ok(f"{tag}: editor shows 'Open in CAD' for the upload", href and "cad.html?bid=" in href, href)
            pg.click("#editOpenCad")
        else:                     # path 2: CAD's own Open menu
            pg.goto(URL + "/static/cad.html"); pg.wait_for_timeout(800)
            pg.click("#cwOpen"); pg.set_input_files("#cwFile", stl)
        wait(pg, "() => window.__cad.S.scene && window.__cad.S.scene.bodies.length === 1")
        pg.wait_for_timeout(600)
        ok(f"{tag}: History shows Import 01", "Import 01" in pg.inner_text("#cwHist"), pg.inner_text("#cwHist"))
        pg.evaluate("window.__cad.viewAlong(new window.__cad.V3(0.8,-1.2,1.1))"); pg.wait_for_timeout(400)
        x, y = scr(pg, [10, 5, 12]); pg.mouse.click(x, y); pg.wait_for_timeout(300)
        ok(f"{tag}: tapping the top face selects body + face", pg.evaluate("!!window.__cad.S.selFace && Math.abs(window.__cad.S.selFace.normal.z - 1) < 1e-3"))
        pg.keyboard.press("k"); pg.wait_for_timeout(200)
        ok(f"{tag}: sketch offers the picked face", "Picked face" in pg.inner_text("#cwTool"))
        pg.click("#tApply"); pg.wait_for_timeout(600)
        pg.click(".cw-tool[data-tool=circle]")
        S = "window.__cad.S.sk.F"
        def at(u, v):
            return scr(pg, pg.evaluate(f"(() => {{ const F = {S}; return F.o.clone().addScaledVector(F.x,{u}).addScaledVector(F.y,{v}).toArray(); }})()"))
        for uv in ((-10, 0), (-4, 0)):
            pg.mouse.click(*at(*uv)); pg.wait_for_timeout(100)
        for uv in ((10, 0), (14, 0)):
            pg.mouse.click(*at(*uv)); pg.wait_for_timeout(100)
        ok(f"{tag}: two circles drawn on the face", pg.evaluate("window.__cad.S.sk.entities.length") == 2)
        pg.keyboard.press("Enter"); pg.wait_for_timeout(1200)
        pg.click("#tMode [data-v=cut]"); pg.click("#tDir [data-v=down]"); pg.fill("#tDist", "20"); pg.click("#tApply")
        wait(pg, "() => window.__cad.S.scene.ops.length === 1")
        pg.wait_for_timeout(800)
        vol = pg.evaluate("window.__cad.S.scene.analysis.volume_mm3")
        ok(f"{tag}: cut two holes through the imported part", abs(vol - (60 * 40 * 12 - 3.14159 * (36 + 16) * 12)) < 40, vol)
        pg.evaluate("window.__cad.openStep(1)"); pg.wait_for_timeout(300)
        pg.screenshot(path=f"{OUT}/edit-imported{'' if tag == 'desktop' else '-ipad'}.png")
        pg.evaluate("window.__cad.openStep(0)")
        pg.keyboard.press("s"); pg.wait_for_timeout(200); pg.fill("#tF", "1.5"); pg.click("#tApply")
        wait(pg, "() => window.__cad.S.scene.ops.length === 2")
        ok(f"{tag}: scale the imported body", abs(pg.evaluate("window.__cad.S.scene.analysis.size_mm[0]") - 90) < 0.01)
        ok(f"{tag}: Open in Slicer link + downloads ready", "edit=" in pg.get_attribute("#cwToSlicer", "href") and pg.get_attribute("#cwDlStl", "href").endswith("/stl"))
        ok(f"{tag}: no JS errors", not errs, errs[:3])
    b.close()
print("ALL PASS" if not bad else f"{len(bad)} FAIL")
sys.exit(1 if bad else 0)
