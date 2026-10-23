"""Beginner shapes palette + lessons in Chromium at 1280 / 390 / 320 px (touch on phones).   python tests/ui_cad_beginner.py URL"""
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


SMALL = """(sel) => [...document.querySelectorAll(sel)].filter(e => e.offsetParent)
  .map(e => e.getBoundingClientRect()).filter(r => r.height < 44 || r.width < 44).length"""
TAPS = "#cwTool button, #cwTool .cw-toggle, #cwLesson button, #cwLearn, [data-tool=shapes]"
# the lesson card must not sit on top of anything the user needs to tap (tool panel, rail, pills, top bar)
COVER = """() => {
  // the part of an element actually on screen: clipped by every scrolling/clipping ancestor
  const vis = e => { let r = e.getBoundingClientRect(), L = r.left, T = r.top, R = r.right, B = r.bottom;
    for (let p = e.parentElement; p; p = p.parentElement) { const s = getComputedStyle(p);
      if (s.overflow !== 'visible' || s.overflowX !== 'visible') { const q = p.getBoundingClientRect();
        L = Math.max(L, q.left); T = Math.max(T, q.top); R = Math.min(R, q.right); B = Math.min(B, q.bottom); } }
    return R > L && B > T ? {left: L, top: T, right: R, bottom: B} : null; }; const c = document.querySelector('#cwLesson'); if (c.hidden) return 0; const a = c.getBoundingClientRect();
  return [...document.querySelectorAll('#cwTool button, #cwTool input, #cwTool select, .cw-tool, .cw-pill, .cw-top .cw-btn, .cw-chip')].filter(e => e.offsetParent)
    .map(vis).filter(r => r && r.left < a.right && r.right > a.left && r.top < a.bottom && r.bottom > a.top)
    // only a real cover if the card is what a tap there would hit
    .filter(r => { const t = document.elementFromPoint((Math.max(r.left, a.left) + Math.min(r.right, a.right)) / 2, (Math.max(r.top, a.top) + Math.min(r.bottom, a.bottom)) / 2); return t && c.contains(t); }).length; }"""
step = lambda pg: pg.evaluate("window.__cad.lessons.state.cur ? window.__cad.lessons.state.cur.step : -1")

with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"])
    for tag, vw, vh, touch in (("chrome 1280", 1280, 800, False), ("chrome 390", 390, 844, True), ("chrome 320", 320, 640, True)):
        ctx = b.new_context(viewport={"width": vw, "height": vh}, has_touch=touch, is_mobile=touch, accept_downloads=True)
        pg = ctx.new_page()
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        tap = (lambda x, y: pg.touchscreen.tap(x, y)) if touch else (lambda x, y: pg.mouse.click(x, y))
        pg.goto(URL + "/static/cad.html"); pg.wait_for_timeout(800)
        ok(f"{tag}: no lesson card until asked", pg.is_hidden("#cwLesson"))
        def via(sel, label):   # phone: header extras live in the '…' menu
            if pg.is_visible(sel): pg.click(sel); return
            pg.click("#cwMore"); pg.locator("#cwMoreMenu [role=menuitem]", has_text=label).first.click()
        via("#cwLearn", "Lessons")
        ok(f"{tag}: lesson list opens with 5 lessons", pg.locator("[data-start]").count() == 5)
        txt = pg.inner_text("#cwLesson").lower()
        ok(f"{tag}: plain adult tone (no school / kid words)", not any(w in txt for w in ("kid", "teacher", "class", "student", "homework", "better than")))
        ok(f"{tag}: tap targets >= 44px", (not touch) or pg.evaluate(SMALL, TAPS) == 0, pg.evaluate(SMALL, TAPS))
        pg.click("[data-start=keychain]")
        ok(f"{tag}: step 1 of 5", "Step 1 of 5" in pg.inner_text("#cwLesson"))
        pg.click("#cwLesson [data-l=show]")
        wait(pg, "() => window.__cad.lessons.state.cur.step === 1")
        ok(f"{tag}: Show me opens Shapes and the step checks itself", pg.is_visible("[data-shape=cylinder]"))
        ok(f"{tag}: palette has 8 shapes", pg.locator("[data-shape]").count() == 8)
        ok(f"{tag}: panel fits the width", pg.evaluate("document.querySelector('#cwTool').getBoundingClientRect().right <= innerWidth + 0.5"))
        ok(f"{tag}: card covers nothing tappable", pg.evaluate(COVER) == 0, pg.evaluate(COVER))
        ok(f"{tag}: tap targets >= 44px (palette + card)", (not touch) or pg.evaluate(SMALL, TAPS) == 0, pg.evaluate(SMALL, TAPS))
        pg.click("#shSize [data-v='40']"); pg.check("#shFlat"); pg.click("[data-shape=cylinder]")
        wait(pg, "() => window.__cad.S.scene && window.__cad.S.scene.bodies.length === 1 && window.__cad.lessons.state.cur.step === 2")
        sz = pg.evaluate("window.__cad.S.scene.bodies[0].size")
        ok(f"{tag}: flat large cylinder dropped (40 x 4 mm)", abs(sz[0] - 40) < 0.5 and abs(sz[2] - 4) < 0.01, sz)
        ok(f"{tag}: card still covers nothing tappable", pg.evaluate(COVER) == 0, pg.evaluate(COVER))
        pg.check("#shEdge"); pg.click("[data-shape=hole]")
        wait(pg, "() => window.__cad.lessons.state.cur.step === 3")
        ok(f"{tag}: hole cut, still one body", pg.evaluate("window.__cad.S.scene.bodies.length") == 1 and pg.evaluate("window.__cad.S.scene.ops.at(-1).params.mode") == "cut")
        frames = pg.evaluate("window.__cadFrames"); pg.wait_for_timeout(600)
        ok(f"{tag}: render-on-demand: idle = no frames", pg.evaluate("window.__cadFrames") - frames <= 2)
        # progress survives a reload; the card comes back folded
        pg.reload(); pg.wait_for_timeout(800)
        wait(pg, "() => window.__cad.S.scene && window.__cad.S.scene.bodies.length === 1")
        ok(f"{tag}: progress remembered after reload (step 4, folded)", step(pg) == 3 and pg.evaluate("window.__cad.lessons.state.mini"))
        pg.click("#cwLesson [data-l=mini]")
        pg.click("#cwLesson [data-l=show]")
        ok(f"{tag}: text step opens Text", pg.is_visible("#tTxt"))
        pg.wait_for_timeout(200)   # floats settle on the next frame
        ok(f"{tag}: card covers nothing in the Text panel", pg.evaluate(COVER) == 0, pg.evaluate(COVER))
        pg.fill("#tTxt", "KEY"); pg.click("#tPick")
        pg.evaluate("window.__cad.viewAlong(new window.__cad.V3(0.001,-0.001,1))"); pg.wait_for_timeout(400)
        tap(*scr(pg, [-6, 0, 4])); pg.wait_for_timeout(400)
        if pg.is_visible("#tApply"):
            pg.click("#tApply")
        try:
            wait(pg, "() => window.__cad.lessons.state.cur.step === 4", 30000); ok(f"{tag}: text on the tag advances the lesson", True)
        except TimeoutError as e:
            ok(f"{tag}: text on the tag advances the lesson", False, str(e))
        if pg.is_visible("#cwWarn button"):
            pg.click("#cwWarn button"); ok(f"{tag}: print tip dismissible", pg.is_hidden("#cwWarn"))
        if pg.is_visible("#tCancel"):
            pg.click("#tCancel")
        with pg.expect_download():
            if pg.is_visible("#cwExport"): pg.click("#cwExport"); pg.click("#cwDlStl")
            else: via("#cwDlStl", "Download STL")
        wait(pg, "() => !window.__cad.lessons.state.cur")
        ok(f"{tag}: export finishes the lesson and marks it done", pg.evaluate("window.__cad.lessons.state.done.keychain") is True and "Nice work" in pg.inner_text("#cwLesson"))
        # skip + exit any time
        pg.click("#cwLesson [data-l=list]")
        ok(f"{tag}: done lesson ticked in the list", "✓" in pg.inner_text("[data-start=keychain]"))
        pg.click("[data-start=prep]"); pg.click("#cwLesson [data-l=next]")
        ok(f"{tag}: a step can be skipped", step(pg) == 1)
        pg.click("#cwLesson [data-l=exit]")
        ok(f"{tag}: exit closes the lesson any time", pg.is_hidden("#cwLesson") and step(pg) == -1)
        ok(f"{tag}: no page errors", not errs, errs)
        ctx.close()
    b.close()
print("ALL PASS" if not bad else f"{len(bad)} FAILED: {bad}")
sys.exit(1 if bad else 0)
