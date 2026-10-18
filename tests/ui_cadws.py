"""CAD workspace smoke + screenshots. python tests/ui_cadws.py URL OUTDIR   (TEMP-data server)"""
import sys
from playwright.sync_api import sync_playwright

URL, OUT = sys.argv[1].rstrip("/"), sys.argv[2]
bad = []


def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c:
        bad.append(n)


def wait(pg, js, timeout):
    import time
    t = time.time()
    while time.time() - t < timeout / 1000:
        try:
            if pg.evaluate(js):
                return True
        except Exception:
            pass
        pg.wait_for_timeout(250)
    raise TimeoutError(js)


def click_local(pg, x, y):
    """Tap a sketch-plane point (mm) on the canvas."""
    sx, sy = pg.evaluate("""([x,y]) => { const S = window.__cad.S, THREE_V = S.sk.F; const v = THREE_V.o.clone().addScaledVector(THREE_V.x, x).addScaledVector(THREE_V.y, y);
        const c = document.querySelector('#cwStage canvas'), r = c.getBoundingClientRect(); const p = v.project(window.__cad.cam);
        return [r.left + (p.x + 1) / 2 * r.width, r.top + (1 - p.y) / 2 * r.height]; }""", [x, y])
    pg.mouse.click(sx, sy)
    pg.wait_for_timeout(80)


def run(tag, vw, vh, touch=False):
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=__import__("os").environ.get("CHROME") or None, args=["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"])
        ctx = b.new_context(viewport={"width": vw, "height": vh}, has_touch=touch, device_scale_factor=1)
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: m.type == "error" and errs.append(m.text))
        pg.goto(URL + "/static/cad.html"); pg.wait_for_timeout(1500)
        ok(f"{tag}: rail lists the model tools", pg.locator(".cw-tool[data-tool=extrude]").count() == 1)
        pg.screenshot(path=f"{OUT}/{tag}-1-empty-workspace.png")
        pg.keyboard.press("k"); pg.wait_for_timeout(200)
        pg.click("#tApply"); pg.wait_for_timeout(600)
        ok(f"{tag}: sketch mode", "Sketch" in pg.inner_text("#cwMode"))
        pg.click(".cw-tool[data-tool=rect]")
        click_local(pg, -20, -15); click_local(pg, 20, 15)
        pg.click(".cw-tool[data-tool=circle]")
        click_local(pg, 0, 0); click_local(pg, 6, 0)
        pg.click(".cw-tool[data-tool=circle]")    # toggle off -> select
        n = pg.evaluate("window.__cad.S.sk.entities.length")
        ok(f"{tag}: rectangle + circle drawn", n == 5, n)
        # type a dimension: first line length -> 50
        pg.locator(".cw-dim").first.click(); pg.wait_for_timeout(100)
        pg.keyboard.press("Control+A"); pg.keyboard.type("50"); pg.keyboard.press("Enter"); pg.wait_for_timeout(1200)
        L = pg.evaluate("(() => { const e = window.__cad.S.sk.entities[0]; return Math.hypot(e.p1[0]-e.p0[0], e.p1[1]-e.p0[1]); })()")
        ok(f"{tag}: typed dimension drives the sketch via the solver", abs(L - 50) < 1e-3, L)
        # select circle, show constraints badges
        click_local(pg, 6, 0)
        pg.wait_for_timeout(300)
        pg.screenshot(path=f"{OUT}/{tag}-2-sketch-dimensions-constraints.png")
        pg.keyboard.press("Enter"); pg.wait_for_timeout(1500)
        ok(f"{tag}: finishing the sketch opens Extrude", "Extrude" in pg.inner_text("#cwTool"))
        pg.fill("#tDist", "12"); pg.click("#tApply")
        wait(pg, "() => window.__cad.S.scene && window.__cad.S.scene.bodies.length === 1", 30000)
        pg.wait_for_timeout(800)
        ok(f"{tag}: first extrude made a project + history step", pg.locator("#cwHist li").count() >= 1)
        # fillet all edges as step 2
        pg.evaluate("window.__cad.viewAlong(new (window.__cad.V3)(1,-1.2,0.9))")
        pg.keyboard.press("f"); pg.wait_for_timeout(200); pg.fill("#tR", "1.5"); pg.click("#tApply")
        wait(pg, "() => window.__cad.S.scene.ops.length === 2", 60000)
        pg.wait_for_timeout(800)
        pg.screenshot(path=f"{OUT}/{tag}-3-workspace-model.png")
        pg.evaluate("window.__cad.openStep(1)"); pg.wait_for_timeout(300)
        ok(f"{tag}: history step expands with editable params", pg.locator(".hbody input").count() >= 2)
        pg.screenshot(path=f"{OUT}/{tag}-4-history-step-expanded.png")
        pg.locator(".hbody input[data-k=distance]").fill("20")
        pg.click(".hbody [data-act=save]")
        wait(pg, "() => window.__cad.S.scene.analysis.size_mm[2] > 19.9", 60000)
        ok(f"{tag}: editing step 1 replays step 2", pg.evaluate("window.__cad.S.scene.ops.length") == 2)
        pg.evaluate("window.__cad.openStep(0)")
        pg.click("#cwSection"); pg.wait_for_timeout(200)
        pg.fill("#cwSecPos", "450"); pg.dispatch_event("#cwSecPos", "input"); pg.wait_for_timeout(500)
        pg.screenshot(path=f"{OUT}/{tag}-5-section-view.png")
        pg.click("#cwSection")
        pg.keyboard.press("Control+f"); pg.wait_for_timeout(200)
        pg.keyboard.type("patt"); pg.wait_for_timeout(100)
        ok(f"{tag}: search finds Pattern", "Pattern" in pg.inner_text("#cwSearchList"))
        pg.keyboard.press("Escape")
        pg.click("#tabItems"); pg.wait_for_timeout(200)
        ok(f"{tag}: items panel lists the body + sketch", "Body 1" in pg.inner_text("#cwItems") and "Sketch of step 1" in pg.inner_text("#cwItems"))
        pg.screenshot(path=f"{OUT}/{tag}-6-items-panel.png")
        ok(f"{tag}: no JS errors", not errs, errs[:3])
        b.close()


run("desktop", 1440, 900)
run("ipad", 1024, 768, touch=True)
print("ALL PASS" if not bad else f"{len(bad)} FAIL")
sys.exit(1 if bad else 0)
