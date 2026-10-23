"""Select mode in a real browser at phone size (390 px): pick the sample photo, open 'Choose part of the photo', trace
round the sun with the mouse, see the snapped live mask, press Make it, and get a model that contains ONLY the sun
(relief: a round footprint, outside removed). Then a lithophane with the outside set to Flat.
python tests/ui_selectmode.py URL [SHOT_DIR]"""
import io, json, math, os, sys, time
import numpy as np, trimesh
from playwright.sync_api import sync_playwright
URL = sys.argv[1].rstrip("/"); SHOTS = sys.argv[2] if len(sys.argv) > 2 else None; bad = []


def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c: bad.append(n)


def wait(pg, js, timeout=60000):
    end = time.time() + timeout / 1000
    while time.time() < end:
        if pg.evaluate(f"() => !!({js})"):
            return True
        pg.wait_for_timeout(250)
    raise TimeoutError(js)


def shot(pg, name):
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True); pg.screenshot(path=os.path.join(SHOTS, name), full_page=False)


def trace_sun(pg, stop_at=None):
    """Sun centre (360, 85) r 48 in the 480x360 sample; trace a wobbly lasso at r ~64."""
    bb = pg.locator("#selCanvas").bounding_box()
    sx, sy = bb["width"] / 480, bb["height"] / 360
    pts = [(bb["x"] + (360 + 64 * (1 + .05 * math.sin(5 * a)) * math.cos(a)) * sx,
            bb["y"] + (85 + 64 * (1 + .05 * math.sin(5 * a)) * math.sin(a)) * sy)
           for a in np.linspace(0, 2 * math.pi, 48, endpoint=False)]
    pts = [(min(max(x, bb["x"] + 1), bb["x"] + bb["width"] - 1), min(max(y, bb["y"] + 1), bb["y"] + bb["height"] - 1)) for x, y in pts]
    pg.mouse.move(*pts[0]); pg.mouse.down()
    for i, p in enumerate(pts[1:], 1):
        pg.mouse.move(*p, steps=2)
        if stop_at and i == stop_at:
            shot(pg, "01-tracing.png")
    pg.mouse.up()


def make(pg):
    with pg.expect_response(lambda r: "/api/generate" in r.url, timeout=90000) as ri:
        pg.click("#selUse")
    r = ri.value; return r.status, r.json()


def footprint(pg, j):
    stl = pg.request.get(URL + j["downloads"]["stl"]).body()
    t = trimesh.load(io.BytesIO(stl), file_type="stl")
    down = t.area_faces[t.face_normals[:, 2] < -0.99].sum()
    return t, down / (t.extents[0] * t.extents[1])


def run(name, launch):
    try: b = launch()
    except Exception as e: print(f"SKIP {name}: {str(e).splitlines()[0][:80]}"); return
    pg = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, has_touch=True)
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL + "/#studio"); pg.wait_for_timeout(800)
    pg.click("#modeCards label[data-mode=relief]")
    with pg.expect_response(lambda r: "/api/generate" in r.url, timeout=90000) as ri:
        pg.click("#sSample")                                     # Beginner: builds the whole photo straight away
    whole = ri.value.json()
    ok(f"{name}: whole photo builds first (no selection sent)", "select" not in (whole.get("params") or {}), whole.get("params"))
    ok(f"{name}: the Select bar appears after the photo", pg.is_visible("#selOpen") and "whole photo" in pg.inner_text("#selState"))
    pg.click("#selOpen"); wait(pg, "window.zeimSelectState.rgb")
    pg.locator("#selPanel").scroll_into_view_if_needed(); pg.wait_for_timeout(300)
    small = pg.evaluate("""[...document.querySelectorAll('#selPanel button,#selOpen,#selPanel label.inl,#selPanel input[type=range]')].filter(e=>e.offsetParent).filter(e=>{const r=e.getBoundingClientRect();return r.height<43.5||(e.tagName==='BUTTON'&&r.width<43.5)}).map(e=>e.id||e.textContent.trim())""")
    ok(f"{name}: every tool is at least 44 px", not small, small)
    ok(f"{name}: the photo area blocks page scroll / browser zoom while drawing",
       pg.evaluate("getComputedStyle(document.querySelector('#selCanvas')).touchAction") == "none")
    y0 = pg.evaluate("scrollY")
    trace_sun(pg, stop_at=30)
    ok(f"{name}: the page did not scroll while tracing", pg.evaluate("scrollY") == y0)
    area = pg.evaluate("window.zeimSelectState.area")
    sun = math.pi * 48 ** 2 / (480 * 360)
    ok(f"{name}: the outline snapped to the sun (selected area ~ the sun, not the looser trace)", 0.75 * sun < area < 1.3 * sun, (area, sun))
    ok(f"{name}: status says the selection is used", "selection" in pg.inner_text("#selState"))
    pg.locator("#selStage").scroll_into_view_if_needed(); shot(pg, "02-selected-mask.png")
    # tools: undo / invert / clear round-trip
    pg.click("#selInvert"); inv = pg.evaluate("window.zeimSelectState.area")
    ok(f"{name}: Invert flips the selection", abs(inv - (1 - area)) < 0.01, (inv, area))
    pg.click("#selUndo"); ok(f"{name}: Undo goes back", abs(pg.evaluate("window.zeimSelectState.area") - area) < 1e-6)
    # pinch zoom with two fingers (synthetic pointer events: draws nothing, zooms)
    pg.evaluate("""(()=>{const c=document.querySelector('#selCanvas'),r=c.getBoundingClientRect(),cx=r.left+r.width/2,cy=r.top+r.height/2;
      const ev=(t,id,x)=>c.dispatchEvent(new PointerEvent(t,{pointerId:id,clientX:x,clientY:cy,bubbles:true,pointerType:'touch'}));
      ev('pointerdown',11,cx-20);ev('pointerdown',12,cx+20);ev('pointermove',11,cx-60);ev('pointermove',12,cx+60);ev('pointerup',11,cx-60);ev('pointerup',12,cx+60);})()""")
    z = pg.evaluate("window.zeimSelectState.zoom")
    ok(f"{name}: two-finger pinch zooms and does not add a stroke", z > 2 and len(pg.evaluate("window.zeimSelectState.paths")) == 1, z)
    pg.click("#selFit")
    st, j = make(pg)
    ok(f"{name}: Make it from my selection builds", st == 200 and j.get("stats", {}).get("watertight"), (st, str(j)[:300]))
    ok(f"{name}: the selection is saved with the build", bool(j.get("params", {}).get("select", {}).get("mask")))
    t, ratio = footprint(pg, j)
    ok(f"{name}: the model is ONLY the sun: a round footprint (area/bbox ~ pi/4), not the 4:3 photo",
       0.65 < ratio < 0.9 and abs(t.extents[0] - t.extents[1]) < 0.15 * t.extents[0], (ratio, t.extents))
    wait(pg, "document.querySelector('#result') && !document.querySelector('#result').hidden")
    pg.wait_for_timeout(1200); pg.locator("#viewer").scroll_into_view_if_needed(); pg.wait_for_timeout(600)
    shot(pg, "03-result-relief.png")
    # lithophane: outside Flat
    pg.click("#modeCards label[data-mode=lithophane]"); pg.wait_for_timeout(300)
    pg.locator("#selPanel").scroll_into_view_if_needed()
    ok(f"{name}: lithophane shows the outside choice", pg.is_visible("#selOutside"))
    pg.check("#selOutside input[value=flat]"); pg.wait_for_timeout(300)
    pg.locator("#selStage").scroll_into_view_if_needed(); shot(pg, "04-litho-flat-preview.png")
    st, j = make(pg)
    sel = j.get("params", {}).get("select", {})
    ok(f"{name}: lithophane builds with the outside flat", st == 200 and sel.get("outside") == "flat", (st, sel.get("outside")))
    pg.wait_for_timeout(1200); pg.locator("#viewer").scroll_into_view_if_needed(); pg.wait_for_timeout(600)
    shot(pg, "05-result-litho-flat.png")
    # Use whole photo skips the selection
    with pg.expect_response(lambda r: "/api/generate" in r.url, timeout=90000) as ri:
        pg.locator("#selWhole").scroll_into_view_if_needed(); pg.click("#selWhole")
    ok(f"{name}: Use whole photo sends no selection", "select" not in ri.value.json().get("params", {}))
    ok(f"{name}: no page errors", not errs, errs)
    b.close()
    if not bad: print(f"PASS {name}")


with sync_playwright() as p:
    run("chrome", lambda: p.chromium.launch())
    SHOTS = None
    run("webkit", lambda: p.webkit.launch())
sys.exit(1 if bad else 0)
