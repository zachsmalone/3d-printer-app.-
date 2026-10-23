"""G-code preview tools in Chromium at 1280 / 390 / 320 px: code panel synced to the layer slider (lazy Range reads,
virtual list), 'Pause at this layer' add/remove + the new download contains the pause, problem marker jump, height jump,
44 px targets, no sideways scroll, render on demand.   python tests/ui_gcode_tools.py URL"""
import os, shutil, sys, tempfile
import trimesh
from playwright.sync_api import sync_playwright
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__))); import zws_open; zws_open.install()   # C: phone panels start as chips
sys.path.insert(0, os.path.dirname(__file__))
from ui_gcode_preview import ok, wait, slice_cube, bad
URL = sys.argv[1].rstrip("/")


def run(p, stl, width):
    name = f"chromium {width}px"; phone = width < 600
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": width, "height": 900}, has_touch=phone, is_mobile=phone, device_scale_factor=2 if phone else 1)
    pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    slice_cube(pg, stl)
    ok(f"{name}: worker finished", wait(pg, "window.__gcDone", 60000))
    n = int(pg.get_attribute("#gcRange", "max"))
    # markers: the test model has an island and an overhang
    ok(f"{name}: trouble spots listed with honest copy", pg.locator("#gcMarks").is_visible() and "not a diagnosis" in pg.inner_text("#gcMarks"), pg.inner_text("#spOut")[:300])
    ok(f"{name}: code panel collapsed on phones, open on desktop", pg.evaluate("document.querySelector('#gcCodeBox').open") == (not phone))
    if phone:
        pg.click("#gcCodeSum")
    mk = pg.locator("#gcMarkList [data-mk]").first; txt = mk.inner_text()
    import re
    want = int(re.search(r"layer (\d+)", txt).group(1)); mk.click()
    ok(f"{name}: marker jumps to its layer", f"Layer {want} of" in pg.inner_text("#gcInfo"), (txt, pg.inner_text("#gcInfo")))
    ok(f"{name}: code panel shows that layer", wait(pg, f"window.__gcCode && window.__gcCode.layer === {want}", 10000), pg.evaluate("window.__gcCode"))
    c = pg.evaluate("window.__gcCode")
    ok(f"{name}: layer code starts at the layer change", c["first"].startswith(";LAYER_CHANGE"), c)
    rows = pg.locator("#gcCode .r").count()
    ok(f"{name}: virtual list (rows in DOM << lines)", 0 < rows < 60 and (c["count"] < 60 or rows < c["count"]), (rows, c["count"]))
    ok(f"{name}: first printing move highlighted", pg.locator("#gcCode .r.hl").count() == 1)
    # slider sync
    pg.focus("#gcRange"); pg.keyboard.press("Home")
    ok(f"{name}: code follows the slider (layer 1)", wait(pg, "window.__gcCode.layer === 1", 10000), pg.evaluate("window.__gcCode"))
    l1 = pg.evaluate("window.__gcCode.line")
    pg.keyboard.press("ArrowRight")
    ok(f"{name}: code follows the slider (layer 2, later lines)", wait(pg, "window.__gcCode.layer === 2", 10000) and pg.evaluate("window.__gcCode.line") > l1)
    # height jump
    pg.fill("#gcJumpV", "5"); pg.select_option("#gcJumpU", "z"); pg.click("#gcJumpGo")
    info = pg.inner_text("#gcInfo"); m = re.search(r"Layer (\d+) of .* Z ([\d.]+)", info)
    ok(f"{name}: height jump lands on the layer printing 5 mm", m and 5.0 <= float(m.group(2)) < 5.5 and "layer" in pg.inner_text("#gcJumpMsg"), (info, pg.inner_text("#gcJumpMsg")))
    pg.fill("#gcJumpV", "7"); pg.select_option("#gcJumpU", "layer"); pg.click("#gcJumpGo")
    ok(f"{name}: layer jump", "Layer 7 of" in pg.inner_text("#gcInfo"))
    ok(f"{name}: code panel synced after jump", wait(pg, "window.__gcCode.layer === 7", 10000))
    # pauses
    pg.click("#gcPauseBox summary")
    note = pg.inner_text("#gcPauseNote")
    cmd = pg.input_value("#gcPauseCmd")
    ok(f"{name}: firmware command named (default generic printer -> user picks or guess)", ("Using" in note and cmd) or "Pick" in note, note)
    if not cmd:
        pg.select_option("#gcPauseCmd", "M600"); cmd = "M600"
    pg.click("#gcPauseAdd")
    pg.fill("#gcJumpV", "12"); pg.click("#gcJumpGo"); pg.click("#gcPauseAdd")
    pg.fill("#gcJumpV", "20"); pg.click("#gcJumpGo"); pg.click("#gcPauseAdd")
    ok(f"{name}: three pauses listed", pg.locator("#gcPauseList li").count() == 3, pg.inner_text("#gcPauseList"))
    pg.click("[data-rm='12']")
    ok(f"{name}: pause removed", pg.locator("#gcPauseList li").count() == 2 and "Layer 12" not in pg.inner_text("#gcPauseList"))
    href = pg.get_attribute("#gcPauseDl", "href")
    ok(f"{name}: download names the command", cmd in pg.inner_text("#gcPauseDl") and "2 pauses" in pg.inner_text("#gcPauseDl"))
    body = pg.request.get(URL + href).text()
    orig = pg.request.get(URL + pg.get_attribute("#spOut a[download].primary", "href")).text()
    lines = body.split("\n")
    ok(f"{name}: download has the pauses at layers 7 and 20, nothing at 12",
       body.count(f"\n{cmd}\n") == 2 and "start of layer 7 " in body and "start of layer 20 " in body and "layer 12 " not in body, href)
    ok(f"{name}: original G-code unchanged", f"\n{cmd}\n" not in orig and len(body) > len(orig))
    i = lines.index(cmd); ok(f"{name}: pause sits right before a layer change", lines[i + 1] == ";LAYER_CHANGE", lines[i - 2:i + 3])
    # dismiss markers, layout
    pg.click("#gcMarksX"); ok(f"{name}: trouble spots dismissible", pg.locator("#gcMarks").is_hidden())
    sz = pg.evaluate("[...document.querySelectorAll('#gcPrev button, #gcPrev summary, #gcPrev select, #gcJumpV, #gcPauseDl')].filter(e => e.offsetParent).map(b => { const r = b.getBoundingClientRect(); return [b.id || b.textContent.slice(0, 12), Math.round(Math.min(r.width, r.height))]; })")
    ok(f"{name}: 44 px targets", all(v >= 44 for _, v in sz), [s for s in sz if s[1] < 44])
    ok(f"{name}: no sideways scroll", pg.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), pg.evaluate("[document.documentElement.scrollWidth, innerWidth]"))
    pg.wait_for_timeout(500); f0 = pg.evaluate("window.__gcFrames"); pg.wait_for_timeout(1000)
    ok(f"{name}: render on demand", pg.evaluate("window.__gcFrames") == f0)
    ok(f"{name}: no page errors", not errs, errs)
    b.close()


d = tempfile.mkdtemp(prefix="zeim-gctools-")
try:
    stl = os.path.join(d, "m.stl")
    post = trimesh.creation.box([10, 10, 20]).apply_translation([0, 0, 10])
    shelf = trimesh.creation.box([24, 24, 2]).apply_translation([0, 0, 21])      # overhang at 20 mm
    fl = trimesh.creation.box([5, 5, 4]).apply_translation([14, 0, 10])         # island from 8 mm
    trimesh.util.concatenate([post, shelf, fl]).export(stl)
    with sync_playwright() as p:
        for w in (1280, 390, 320):
            run(p, stl, w)
finally:
    shutil.rmtree(d, ignore_errors=True)
print(f"FAIL: {len(bad)} failed" if bad else "PASS chrome (chromium G-code tools)")
sys.exit(1 if bad else 0)
