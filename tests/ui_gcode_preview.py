"""3D G-code preview in Chromium (Playwright): slice a cube from the Slicer, the three.js preview streams the G-code
through the Web Worker, then: layer slider (keyboard + buttons), Play/Pause, legend toggles (travel off by default),
layer/height readout, time/filament line, render on demand (no frames while idle), 44 px targets, no sideways scroll
at 390 and 320 px, DPR capped at 1.5 on a touch phone.
Optional big-file run: GC_BIG=/path/file.gcode GC_SLICES=<server PHOTO3D_DATA>/slices serves that file as the slice's G-code and reports parse time and the
longest main-thread task while it streams.   python tests/ui_gcode_preview.py URL"""
import io, os, re, shutil, sys, tempfile, time
import trimesh
from playwright.sync_api import sync_playwright
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__))); import zws_open; zws_open.install()   # C: phone panels start as chips
URL = sys.argv[1].rstrip("/"); bad = []


def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c: bad.append(n)


def wait(pg, js, timeout=60000):
    end = time.time() + timeout / 1000
    while time.time() < end:
        if pg.evaluate(f"() => !!({js})"):
            return True
        pg.wait_for_timeout(200)
    return False


LONGTASKS = """window.__lt = []; try { new PerformanceObserver(l => { for (const e of l.getEntries()) window.__lt.push(e.duration); })
  .observe({ type: 'longtask' }); } catch (e) {}"""


def slice_cube(pg, stl):
    pg.goto(URL + "/#edit"); pg.wait_for_timeout(800)
    pg.set_input_files("#editFile", stl)
    pg.wait_for_selector("#editResult:not([hidden])", timeout=60000)
    pg.wait_for_selector("#spGo", timeout=30000)
    pg.click("#spGo")
    pg.wait_for_selector("#spOut .slicestats, #spOut [role=alert]", timeout=180000)


def lit_pixels(pg):
    from PIL import Image
    im = Image.open(io.BytesIO(pg.locator("#gcStage").screenshot())).convert("RGB")
    return sum(1 for r, g, b in im.getdata() if max(r, g, b) > 120)


def main_run(p, stl, width):
    name = f"chromium {width}px touch"
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": width, "height": 800}, device_scale_factor=3, has_touch=True, is_mobile=True)
    pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    slice_cube(pg, stl)
    ok(f"{name}: preview section shown after slicing", pg.locator("#spOut #gcPrev").count() == 1, pg.inner_text("#spOut")[:400])
    ok(f"{name}: worker finished", wait(pg, "window.__gcDone", 60000), pg.inner_text("#gcPrev")[:400])
    done = pg.evaluate("window.__gcDone"); n = int(pg.get_attribute("#gcRange", "max"))
    ok(f"{name}: many layers (cube 10 mm)", n > 20 and n == done["layers"], (n, done))
    ok(f"{name}: progress hidden when done", pg.locator("#gcProgWrap").is_hidden())
    ok(f"{name}: starts on the top layer", f"Layer {n} of {n}" in pg.inner_text("#gcInfo"), pg.inner_text("#gcInfo"))
    pg.focus("#gcRange"); pg.keyboard.press("Home")
    ok(f"{name}: keyboard Home -> layer 1 with Z height", "Layer 1 of" in pg.inner_text("#gcInfo") and "Z 0.2" in pg.inner_text("#gcInfo"), pg.inner_text("#gcInfo"))
    pg.keyboard.press("ArrowRight")
    ok(f"{name}: ArrowRight -> layer 2, aria-valuetext follows", "Layer 2 of" in pg.inner_text("#gcInfo") and "Layer 2" in (pg.get_attribute("#gcRange", "aria-valuetext") or ""))
    pg.click("#gcNextL"); ok(f"{name}: Next button", "Layer 3 of" in pg.inner_text("#gcInfo"))
    pg.click("#gcPrevL"); ok(f"{name}: Previous button", "Layer 2 of" in pg.inner_text("#gcInfo"))
    pg.click("#gcPlay"); ok(f"{name}: Play sets aria-pressed", pg.get_attribute("#gcPlay", "aria-pressed") == "true")
    pg.wait_for_timeout(500); lay = int(pg.input_value("#gcRange"))
    ok(f"{name}: Play advances layers", lay > 2, lay)
    pg.click("#gcPlay"); ok(f"{name}: Pause", pg.get_attribute("#gcPlay", "aria-pressed") == "false")
    pg.focus("#gcRange"); pg.keyboard.press("End")
    leg = pg.inner_text("#gcLegend")
    ok(f"{name}: legend names the types", all(t in leg for t in ["Outer wall", "Inner wall", "Infill", "Support", "Skirt", "Travel"]), leg)
    ok(f"{name}: travel hidden by default, walls shown", not pg.is_checked("[data-gct=travel]") and pg.is_checked("[data-gct=outer]"))
    ok(f"{name}: time/filament line", "filament" in pg.inner_text("#gcEst") and re.search(r"\d+ g", pg.inner_text("#gcEst")), pg.inner_text("#gcEst"))
    pg.wait_for_timeout(400)
    lit = lit_pixels(pg); lines0 = pg.evaluate("window.__gcLines")
    ok(f"{name}: lines are drawn", lit > 150 and lines0 > 100, (lit, lines0))
    f0 = pg.evaluate("window.__gcFrames"); pg.wait_for_timeout(1200); f1 = pg.evaluate("window.__gcFrames")
    ok(f"{name}: render on demand (no frames while idle)", f1 == f0, (f0, f1))
    for t in ["outer", "inner", "infill", "solid", "skirt", "other", "support"]:
        pg.uncheck(f"[data-gct={t}]")
    pg.wait_for_timeout(300)
    lines1 = pg.evaluate("window.__gcLines")
    ok(f"{name}: unticking every type draws no lines (and re-renders)", lines1 == 0 and pg.evaluate("window.__gcFrames") > f1, (lines0, lines1))
    pg.check("[data-gct=outer]")
    sz = pg.evaluate("[...document.querySelectorAll('#gcPrev button, #gcPrev .gcchip, #gcRange')].filter(b => b.getClientRects().length).map(b => { const r = b.getBoundingClientRect(); return Math.round(Math.min(r.width, r.height)); })")
    ok(f"{name}: 44 px targets", all(v >= 44 for v in sz), sz)
    ok(f"{name}: no sideways scroll", pg.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), pg.evaluate("[document.documentElement.scrollWidth, innerWidth]"))
    dpr = pg.evaluate("(() => { const c = document.querySelector('#gcStage canvas'); return c.width / c.getBoundingClientRect().width; })()")
    ok(f"{name}: DPR capped at 1.5 on touch (device 3x)", dpr <= 1.51, dpr)
    ok(f"{name}: stage and slider are labelled", pg.get_attribute("#gcStage", "aria-label") and pg.locator("label[for=gcRange]").count() == 1)
    ok(f"{name}: no page errors", not errs, errs)
    b.close()


def big_run(p, stl, path):
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    # serve the big file from the REAL server (streams like production): link it in as a slice, point the reply at it
    fake = "b" * 32; dd = os.path.join(os.environ["GC_SLICES"], fake); os.makedirs(dd, exist_ok=True)
    tgt = os.path.join(dd, "model.gcode")
    if os.path.lexists(tgt): os.remove(tgt)
    os.symlink(os.path.abspath(path), tgt)

    def swap(route):
        import json
        r = route.fetch(); j = r.json(); j["downloads"]["gcode"] = f"/api/slice/{fake}/gcode"
        route.fulfill(response=r, body=json.dumps(j))
    pg.route("**/api/slice", lambda r: swap(r) if r.request.method == "POST" else r.continue_())
    pg.add_init_script(LONGTASKS)
    slice_cube(pg, stl)
    pg.wait_for_selector("#gcPrev", timeout=60000); pg.evaluate("window.__lt = []")   # only what happens while the G-code streams
    t0 = time.time(); prog = []
    while time.time() - t0 < 600 and not pg.evaluate("window.__gcDone"):
        prog.append(pg.evaluate("document.querySelector('#gcProg')?.value || 0")); pg.wait_for_timeout(250)
    pg.wait_for_timeout(1500)   # include the first full render after parsing
    d = pg.evaluate("window.__gcDone"); lt = pg.evaluate("window.__lt")
    mb = os.path.getsize(path) / 1e6
    print(f"BIG {mb:.0f} MB: worker {d and d['ms']} ms, layers {d and d['layers']}, wall {time.time() - t0:.1f}s, "
          f"main-thread long tasks while streaming+first render: max {max(lt or [0]):.0f} ms, count {len(lt or [])}, sum {sum(lt or [0]):.0f} ms, progress samples {sorted(set(prog))[:12]}, js timings {pg.evaluate('window.__gcT')}")
    ok("big: finished", bool(d), d)
    ok("big: progress shown while streaming", len(set(prog)) > 2, sorted(set(prog)))
    ok("big: slider still responds", pg.focus("#gcRange") or pg.keyboard.press("Home") or "Layer 1 of" in pg.inner_text("#gcInfo"))
    ok("big: no page errors", not errs, errs)
    b.close()


d = tempfile.mkdtemp(prefix="zeim-gcprev-")
try:
    stl = os.path.join(d, "cube.stl"); trimesh.creation.box([20, 20, 10]).export(stl)
    with sync_playwright() as p:
        for w in (390, 320):
            main_run(p, stl, w)
        if os.environ.get("GC_BIG"):
            big_run(p, stl, os.environ["GC_BIG"])
finally:
    shutil.rmtree(d, ignore_errors=True)
print(f"FAIL: {len(bad)} failed" if bad else "PASS chrome (chromium G-code preview)")
sys.exit(1 if bad else 0)
