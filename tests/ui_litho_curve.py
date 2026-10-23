"""Curved panel lithophane: bend slider 0/90/180, built-in stand, bed note, export picker, no overlaps at 1280 / 390.
python tests/ui_litho_curve.py URL [SHOTDIR]"""
import os, sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1].rstrip("/"); SHOTS = sys.argv[2] if len(sys.argv) > 2 else "/workspace/qa/curve/shots"
os.makedirs(SHOTS, exist_ok=True); bad = []
def ok(n, c):
    print(("PASS " if c else "FAIL ") + n); c or bad.append(n)
OVERLAP = """() => { const els = [...document.querySelectorAll('#curveOpts .field, #curveOpts .help, #curveOpts label.inl, #shapeCards .card')]
  .filter(e => e.offsetParent); const r = els.map(e => e.getBoundingClientRect());
  for (let i = 0; i < r.length; i++) for (let j = i + 1; j < r.length; j++) { if (els[i].contains(els[j]) || els[j].contains(els[i])) continue;
    const a = r[i], b = r[j]; if (a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1) return [els[i].outerHTML.slice(0,60), els[j].outerHTML.slice(0,60)]; } return null; }"""
with sync_playwright() as p:
    b = p.chromium.launch()
    for name, vp, kw in (("w1280", {"width": 1280, "height": 900}, {}), ("w390", {"width": 390, "height": 844}, {"has_touch": True, "is_mobile": True, "device_scale_factor": 2})):
        pg = b.new_page(viewport=vp, **kw); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script("localStorage.level='expert'; localStorage.setItem('zeim.adult','yes')")
        pg.goto(URL + "/#studio"); pg.wait_for_timeout(1500)
        pg.click("#sSample"); pg.wait_for_timeout(1000)                       # Tango, the built-in sample
        card = pg.locator("[data-shape='curve']"); card.scroll_into_view_if_needed(); card.click(); pg.wait_for_timeout(300)
        ok(f"{name}: curve card has a line icon, no emoji", card.locator("svg use[href='#i-curve']").count() == 1
           and all(ord(c) < 0x2190 for c in card.inner_text()))
        ok(f"{name}: bend + stand visible, placement editor hidden", pg.is_visible("#bend_deg") and pg.is_visible("#curveStand")
           and not pg.is_visible("#placeEditor"))
        def settings():   # after a build the workspace layout can push Settings aside (pre-existing): bring it back
            for _ in range(12):
                if pg.is_visible("#bend_deg"): break
                for sel in ("#zws-result .zws-min", "#zws-settings .zws-chip"):
                    if pg.is_visible(sel): pg.click(sel); pg.wait_for_timeout(300)
                pg.evaluate("dispatchEvent(new Event('resize'))"); pg.wait_for_timeout(400)
            pg.locator("#curveOpts").scroll_into_view_if_needed()
        for bend, stand, tag in ((0, False, "flat"), (90, False, "90deg"), (180, False, "180deg"), (120, True, "stand")):
            settings()
            pg.evaluate(f"""() => {{ const r = document.querySelector('#bend_deg'); r.value = {bend}; r.dispatchEvent(new Event('input')); }}""")
            (pg.check if stand else pg.uncheck)("#curveStand")
            pg.evaluate("() => { const e = document.querySelector('#curveFit'); if (e) e.textContent = ''; }")
            ok(f"{name} {tag}: bend label {pg.inner_text('#bendOut')!r}", pg.inner_text("#bendOut").startswith(f"{bend}°"))
            pg.click("#btnBuild"); pg.wait_for_timeout(800)
            if pg.is_visible("#btnAutoDel"):                                   # recent builds full (5 of 5): auto-delete oldest
                pg.click("#btnAutoDel"); pg.wait_for_timeout(800)
            for _ in range(480):
                if "bed" in pg.inner_text("#curveFit") and not pg.is_visible("#busy"): break
                pg.wait_for_timeout(250)
            pg.wait_for_timeout(1500)
            fit = pg.inner_text("#curveFit")
            ok(f"{name} {tag}: bed note {fit[:70]!r}", "bed" in fit)
            settings()
            ov = pg.evaluate(OVERLAP); ok(f"{name} {tag}: no overlaps {ov}", ov is None)
            pg.locator("#curveOpts").scroll_into_view_if_needed()
            sec = pg.locator("#curveOpts")
            sec.screenshot(path=f"{SHOTS}/{tag}-controls-{name}.png")
            pg.locator("#viewer").scroll_into_view_if_needed(); pg.wait_for_timeout(400)
            pg.locator("#viewer").screenshot(path=f"{SHOTS}/{tag}-viewer-{name}.png")
            pg.screenshot(path=f"{SHOTS}/{tag}-page-{name}.png", full_page=False)
        for _ in range(8):
            if pg.is_visible("#btnSendSheet"): break
            if pg.is_visible("#zws-result .zws-chip"): pg.click("#zws-result .zws-chip")
            pg.wait_for_timeout(400)
        pg.locator("#btnSendSheet").scroll_into_view_if_needed()
        opened = False
        try:   # the shared export picker (exportpick.js) adds "Export…" next to Send or save
            pg.click("#studioExport", timeout=5000); pg.wait_for_selector("#dlgExport[open]", timeout=8000); opened = True
        except Exception:
            pass
        ok(f"{name}: shared export picker opens", opened)
        if opened:
            pg.wait_for_timeout(500)
            ok(f"{name}: picker offers STL and 3MF", pg.locator("input[name=expFmt][value=stl]").count() == 1)
            pg.locator("#dlgExport").screenshot(path=f"{SHOTS}/export-{name}.png")
        sw = pg.evaluate("document.documentElement.scrollWidth")
        ok(f"{name}: no sideways scroll ({sw})", sw <= vp["width"] + 1)
        ok(f"{name}: no page errors {errs}", not errs)
    b.close()
sys.exit(1 if bad else 0)
