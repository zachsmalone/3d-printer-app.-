"""CAD Text & Emboss in Chromium at 1280 / 390 / 320 px (touch on phones).   python tests/ui_cad_text.py URL"""
import sys, time
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
    raise TimeoutError(js + ' | msg: ' + pg.inner_text('#cwMsg'))


def scr(pg, v):
    return pg.evaluate("""(v) => { const c = document.querySelector('#cwStage canvas'), r = c.getBoundingClientRect();
      const p = new window.__cad.V3(...v).project(window.__cad.cam); return [r.left + (p.x + 1) / 2 * r.width, r.top + (1 - p.y) / 2 * r.height]; }""", v)


SMALL = """() => [...document.querySelectorAll('#cwTool button, #cwTool summary, #cwWarn button, [data-tool=text]')].filter(e => e.offsetParent)
  .map(e => e.getBoundingClientRect()).filter(r => r.height < 44 || r.width < 44).length"""
with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"])
    for tag, vw, vh, touch in (("chrome 1280", 1280, 800, False), ("chrome 390", 390, 844, True), ("chrome 320", 320, 640, True)):
        pg = b.new_context(viewport={"width": vw, "height": vh}, has_touch=touch, is_mobile=touch).new_page()
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        tap = (lambda x, y: pg.touchscreen.tap(x, y)) if touch else (lambda x, y: pg.mouse.click(x, y))
        pg.goto(URL + "/static/cad.html"); pg.wait_for_timeout(800)
        pg.click("[data-tool=text]"); pg.wait_for_selector("#tTxt", timeout=3000)
        ok(f"{tag}: Text tool opens with no model (plate only)", pg.is_visible("#tTxt") and pg.locator("#tTarget button").count() == 1)
        ok(f"{tag}: tap targets >= 44px (pointer:coarse on phones)", (not touch) or pg.evaluate(SMALL) == 0, pg.evaluate(SMALL))
        ok(f"{tag}: Advanced is folded by default", not pg.is_visible("#tRot"))
        ok(f"{tag}: panel fits the width", pg.evaluate("document.querySelector('#cwTool').getBoundingClientRect().right <= innerWidth + 0.5"))
        pg.fill("#tTxt", "ZEIM"); pg.click("#tApply")
        wait(pg, "() => window.__cad.S.scene && window.__cad.S.scene.bodies.length === 1")
        ok(f"{tag}: plate made as step 1", pg.evaluate("window.__cad.S.scene.ops?.length ?? 1") >= 1)
        ok(f"{tag}: canvas touch-action none", pg.evaluate("getComputedStyle(document.querySelector('#cwStage canvas')).touchAction") == "none")
        frames = pg.evaluate("window.__cadFrames"); pg.wait_for_timeout(600)
        ok(f"{tag}: render-on-demand: idle = no frames", pg.evaluate("window.__cadFrames") - frames <= 2)
        pg.evaluate("window.__cad.viewAlong(new window.__cad.V3(0.2,-0.3,1))"); pg.wait_for_timeout(400)
        pg.keyboard.press("Escape") if not touch else None
        pg.click("[data-tool=text]")
        pg.click("#tPick")
        ok(f"{tag}: Pick spot moves the panel out of the way", not pg.is_visible("#cwTool"))
        tap(*scr(pg, [0, 0, 2.5])); pg.wait_for_timeout(400)
        ok(f"{tag}: tapping the model picks the spot", pg.evaluate("!!window.__cad.S.selFace") and "Spot picked" in pg.inner_text("#tWhere") and pg.is_visible("#tApply"))
        ok(f"{tag}: typed text kept after the tap re-renders the panel", pg.input_value("#tTxt") == "ZEIM")
        pg.fill("#tTxt", "ab"); pg.fill("#tSize", "2"); pg.fill("#tDepth", "0.2")
        pg.click("#tApply")
        wait(pg, "() => !!document.querySelector('#cwWarn')", 30000)
        ok(f"{tag}: thin text applied with a print tip, not blocked", pg.evaluate("window.__cad.S.scene.bodies.length") == 1 and "nozzle" in pg.inner_text("#cwWarn"))
        ok(f"{tag}: tip fits the screen", pg.evaluate("(() => { const r = document.querySelector('#cwWarn').getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth + 0.5; })()"))
        pg.click("#cwWarn button")
        ok(f"{tag}: print tip dismissible", pg.locator("#cwWarn").count() == 0)
        if touch and pg.is_visible("#tabHist"): pg.tap("#tabHist"); pg.wait_for_timeout(300)   # phone: History lives in the bottom sheet
        ok(f"{tag}: History shows the text step", "Text 'ab'" in pg.inner_text("#cwHist"))
        ok(f"{tag}: STL export link set", "/api/" in (pg.get_attribute("#cwDlStl", "href") or ""))
        ok(f"{tag}: no page errors", not errs, errs)
        pg.context.close()
    b.close()
print("ALL PASS" if not bad else f"{len(bad)} FAILED")
sys.exit(1 if bad else 0)
