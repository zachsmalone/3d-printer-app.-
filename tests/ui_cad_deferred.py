"""Deferred CAD items in Chromium at 1280 and 390 px: Hinges/Joints, Merge (snap + fuse, non-blocking warning),
Measure face angle, and the big-model "Open simplified copy" banner.   python tests/ui_cad_deferred.py URL [SHOTS_DIR]"""
import os, sys, time
import trimesh
from playwright.sync_api import sync_playwright

URL = sys.argv[1].rstrip("/")
SHOTS = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("CADD_SHOTS", "")
bad = []


def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c:
        bad.append(n)


def wait(pg, js, timeout=90000):
    t = time.time()
    while time.time() - t < timeout / 1000:
        try:
            if pg.evaluate(js):
                return True
        except Exception:
            pass
        pg.wait_for_timeout(250)
    raise TimeoutError(js + " | msg: " + pg.inner_text("#cwMsg"))


def shot(pg, name):
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True); pg.screenshot(path=os.path.join(SHOTS, name))


# panel inside the viewport and not overlapping the rail (both visible)
FIT = """() => { const t = document.querySelector('#cwTool').getBoundingClientRect(), r = document.querySelector('#cwRail');
  const inV = t.left >= -0.5 && t.right <= innerWidth + 0.5;
  if (!r || !r.offsetParent) return inV; const q = r.getBoundingClientRect();
  const over = Math.max(0, Math.min(t.right, q.right) - Math.max(t.left, q.left)) * Math.max(0, Math.min(t.bottom, q.bottom) - Math.max(t.top, q.top));
  return inV && over < 1; }"""
WORDS = ("kid", "child", "teacher", "class", "student", "school", "family", "homework")
EMOJI = "() => /[\\u{1F300}-\\u{1FAFF}\\u{2600}-\\u{27BF}]/u.test(document.querySelector('#cwTool').innerText)"

big = trimesh.creation.icosphere(subdivisions=7, radius=30)       # 327,680 triangles: over the CAD view limit
big.apply_translation([0, 0, 30]); BIG = big.export(file_type="stl")

with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"])
    for tag, vw, vh, touch in (("chrome 1280", 1280, 800, False), ("chrome 390", 390, 844, True)):
        w = f"w{vw}"
        ctx = b.new_context(viewport={"width": vw, "height": vh}, has_touch=touch, is_mobile=touch)
        pg = ctx.new_page()
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(URL + "/static/cad.html"); pg.wait_for_timeout(800)
        ok(f"{tag}: rail has Hinges/Joints and Merge", pg.locator("[data-tool=joints]").count() == 1 and pg.locator("[data-tool=merge]").count() == 1)
        ok(f"{tag}: tool icons are line SVGs", pg.locator("[data-tool=joints] svg path, [data-tool=joints] svg rect").count() > 0)
        pg.evaluate("window.__cad.setTool('joints')"); pg.wait_for_timeout(300)
        ok(f"{tag}: joints panel fits, no overlap", pg.evaluate(FIT))
        txt = pg.inner_text("#cwTool").lower()
        ok(f"{tag}: adult, humble copy", not any(x in txt for x in WORDS) and "simulated" in txt, txt)
        ok(f"{tag}: no emoji", not pg.evaluate(EMOJI))
        shot(pg, f"joints-panel-{w}.png")
        pg.click("#tApply")
        wait(pg, "() => window.__cad.S.scene && window.__cad.S.scene.bodies.length === 2")
        ok(f"{tag}: hinge added as two moving bodies", True)
        ok(f"{tag}: print tip shown and dismissible (never blocks)", pg.is_visible("#cwWarn"))
        shot(pg, f"hinge-added-{w}.png")
        pg.click("#cwWarn button"); ok(f"{tag}: tip dismissed", pg.locator("#cwWarn").count() == 0)
        pg.evaluate("window.__cad.setTool('joints')"); pg.wait_for_timeout(200)
        pg.click("#jKind [data-v=chain]"); pg.wait_for_timeout(150)
        ok(f"{tag}: chain options shown", pg.is_visible("#jK"))
        pg.click("#tApply")
        wait(pg, "() => window.__cad.S.scene.bodies.length === 7")
        ok(f"{tag}: chain of 5 links added", True)
        shot(pg, f"chain-added-{w}.png")
        # Merge: panel, snapping maths, fuse the two hinge leaves (they don't touch -> a dismissible tip, not a block)
        pg.evaluate("window.__cad.setTool('merge')"); pg.wait_for_timeout(300)
        ok(f"{tag}: merge panel fits, no overlap", pg.evaluate(FIT))
        ok(f"{tag}: merge copy is adult", not any(x in pg.inner_text("#cwTool").lower() for x in WORDS))
        shot(pg, f"merge-panel-{w}.png")
        sn = pg.evaluate("""() => { const S = window.__cad.S, b = S.scene.bodies[1], o = S.scene.bodies[0];
          const want = (o.center[0] + o.size[0] / 2 - 0.2) - (b.center[0] - b.size[0] / 2);
          const [d, hit] = window.__mergeSnap(b, [want + 1.2, 0.0]); return [Math.abs(d[0] - want) < 1e-6, !!hit]; }""")
        ok(f"{tag}: drag snaps to a neighbour's side (0.2 mm overlap)", sn == [True, True], sn)
        pg.click("#tApply")
        wait(pg, "() => document.querySelector('#cwWarn') || /Merged/.test(document.querySelector('#cwMsg').textContent) || window.__cad.S.scene.bodies.length < 7")
        ok(f"{tag}: fuse ran and the app is still usable", pg.evaluate("!!window.__cad.S.scene"))
        shot(pg, f"merge-fused-{w}.png")
        if pg.locator("#cwWarn").count(): pg.click("#cwWarn button")
        a = pg.evaluate("[window.__measAngle([0,0,1],[0,0,1]), window.__measAngle([0,0,1],[1,0,0]), window.__measAngle([0,0,1],[0,0,-1])]")
        ok(f"{tag}: measure face angle 0/90/180", [round(x, 6) for x in a] == [0, 90, 180], a)
        # big model banner
        r = pg.request.post(URL + "/api/edit/new", multipart={"file": {"name": "big.stl", "mimeType": "model/stl", "buffer": BIG}})
        j = r.json(); bid = j.get("id") or j["project"]["id"]
        pg.goto(URL + f"/static/cad.html?bid={bid}"); pg.wait_for_timeout(500)
        wait(pg, "() => document.querySelector('#cwBig')")
        btxt = pg.inner_text("#cwBig")
        ok(f"{tag}: big-model banner offers a simplified copy", "Open simplified copy" in btxt and "327,680" in btxt, btxt)
        ok(f"{tag}: banner inside the viewport", pg.evaluate("document.querySelector('#cwBig').getBoundingClientRect().right <= innerWidth + 0.5"))
        shot(pg, f"bigmodel-banner-{w}.png")
        pg.click("#cwBig [data-b=simp]")
        wait(pg, "() => window.__cad.S.scene && window.__cad.S.scene.bodies.length === 1", 180000)
        ok(f"{tag}: simplified copy opens in CAD", pg.locator("#cwBig").count() == 0)
        shot(pg, f"bigmodel-simplified-{w}.png")
        ok(f"{tag}: no page errors", not errs, errs)
        ctx.close()
    b.close()
print("ALL PASS" if not bad else f"FAILED: {bad}")
sys.exit(1 if bad else 0)
