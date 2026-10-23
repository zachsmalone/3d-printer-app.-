"""Phone CAD compact layout in Chromium (touch) at 390x844, 375x667, 320x568, portrait + landscape.
The 3D view covers at least 70% of the screen, the header is one row, the floating toolbars never overlap each other
or the view cube, every control is a 44px target, toolbars drag + snap to an edge and remember it, and
History/Items is a sheet with peek / half / full.   python tests/ui_cad_phone_layout.py URL [SHOTDIR]"""
import sys, os
from playwright.sync_api import sync_playwright
U = sys.argv[1].rstrip("/"); SHOT = sys.argv[2] if len(sys.argv) > 2 else None
VPS = [(390, 844), (375, 667), (320, 568), (844, 390), (667, 375), (568, 320)]
bad = []
GEOM = """() => {
  const R = s => { const e = document.querySelector(s); if (!e || e.hidden || !e.offsetParent) return null; const r = e.getBoundingClientRect(); return r.width && r.height ? {x:r.left,y:r.top,w:r.width,h:r.height,b:r.bottom,r:r.right} : null };
  const st = R('#cwStage'), top = R('.cw-top');
  const vis = [...document.querySelectorAll('.cw-top > *')].filter(e => e.offsetParent && e.getBoundingClientRect().width);
  const rows = new Set(vis.map(e => Math.round(e.getBoundingClientRect().top / 8)));
  const small = [...document.querySelectorAll('.cw-top button, .cw-top a, .zws-p:not([hidden]) button, .cw-tabs button')].filter(e => e.offsetParent && getComputedStyle(e).visibility !== 'hidden')
     .map(e => [e.id || e.dataset.tool || e.className, e.getBoundingClientRect()]).filter(([n, r]) => r.width && (r.width < 43.5 || r.height < 43.5)).map(([n, r]) => n + ' ' + Math.round(r.width) + 'x' + Math.round(r.height));
  const out = [...document.querySelectorAll('.zws-p, .cw-cubewrap')].map(e => e.getBoundingClientRect()).filter(r => r.left < -1 || r.top < -1 || r.right > innerWidth + 1 || r.bottom > innerHeight + 1).length;
  return {share: st.w * st.h / (innerWidth * innerHeight), rows: rows.size, small, out, rail: R('#zws-tools'), quick: R('#zws-quick'), cube: R('#cwStage .cw-cubewrap'), side: R('#cwSide'), stage: st};
}"""
def drag(pg, x0, y0, x1, y1, n=10):
    """a real one-finger touch drag (CDP), like a thumb on a phone"""
    cdp = pg.context.new_cdp_session(pg)
    pt = lambda x, y: [{"x": x, "y": y, "id": 1}]
    cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": pt(x0, y0)})
    for i in range(1, n + 1):
        cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": pt(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n)}); pg.wait_for_timeout(16)
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []}); cdp.detach()
def ov(a, b): return a and b and a["x"] < b["r"] - 1 and b["x"] < a["r"] - 1 and a["y"] < b["b"] - 1 and b["y"] < a["b"] - 1
with sync_playwright() as p:
    br = p.chromium.launch()
    for w, h in VPS:
        tag = f"{w}x{h}"
        c = br.new_context(viewport={"width": w, "height": h}, has_touch=True, is_mobile=True)
        pg = c.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(U + "/static/cad.html"); pg.wait_for_selector("#zws-tools"); pg.wait_for_timeout(700)
        g = pg.evaluate(GEOM)
        if SHOT: pg.screenshot(path=os.path.join(SHOT, f"cad_phone_{tag}.png"))
        if g["share"] < 0.70: bad.append(f"{tag}: view is {g['share']:.0%} of the screen (<70%)")
        if g["rows"] != 1: bad.append(f"{tag}: header has {g['rows']} rows")
        if g["small"]: bad.append(f"{tag}: small targets {g['small'][:6]}")
        if g["out"]: bad.append(f"{tag}: {g['out']} floats off-screen")
        for a, b in (("rail", "quick"), ("rail", "cube"), ("quick", "cube")):
            if ov(g[a], g[b]): bad.append(f"{tag}: {a} overlaps {b}")
        for a in ("rail", "quick", "cube"):
            if ov(g[a], g["side"]): bad.append(f"{tag}: {a} under the sheet")
        if not g["rail"] or not g["quick"]: bad.append(f"{tag}: floats missing"); c.close(); continue
        # "…" menu reaches Export + theme + palette
        pg.tap("#cwMore"); pg.wait_for_selector("#cwMoreMenu:not([hidden])")
        names = pg.eval_on_selector_all("#cwMoreMenu .cw-mi", "e => e.map(x => x.textContent)")
        for need in ("Download STL", "Import STL", "Dark mode", "Look", "Lessons", "Search tools", "Grid"):
            if not any(need in n for n in names): bad.append(f"{tag}: '…' menu lacks {need}")
        if not pg.is_visible("#cwMoreMenu #cwUnits"): bad.append(f"{tag}: units not in '…' menu")
        pg.keyboard.press("Escape")
        # drag the quick cluster to the far edge: it snaps there, stays clear, and is remembered after reload
        q = g["quick"]; gp = pg.locator("#zws-quick .zws-grip").bounding_box(); s = g["stage"]
        tx, ty = s["r"] - 10, s["y"] + s["h"] * 0.6
        drag(pg, gp["x"] + 22, gp["y"] + 22, tx, ty); pg.wait_for_timeout(300)
        want = "right"
        e1 = pg.get_attribute("#zws-quick", "data-edge")
        g2 = pg.evaluate(GEOM)
        for a, b in (("rail", "quick"), ("quick", "cube"), ("rail", "cube")):
            if ov(g2[a], g2[b]): bad.append(f"{tag}: after drag {a} overlaps {b}")
        if e1 != want: bad.append(f"{tag}: dragged cluster on edge {e1}, wanted {want}")
        pg.reload(); pg.wait_for_selector("#zws-tools"); pg.wait_for_timeout(500)
        if pg.get_attribute("#zws-quick", "data-edge") != want: bad.append(f"{tag}: cluster edge not remembered")
        # keyboard: Enter on the grip moves it to the next edge
        pg.focus("#zws-quick .zws-grip"); pg.keyboard.press("Enter"); pg.wait_for_timeout(200)
        if pg.get_attribute("#zws-quick", "data-edge") == want: bad.append(f"{tag}: Enter on grip did not move the cluster")
        pg.evaluate("localStorage.clear()")
        # sheet: peek → half → full by tapping the handle; drag down snaps back to peek
        sz = lambda: pg.evaluate("(() => { const r = document.querySelector('#cwSide').getBoundingClientRect(); return innerWidth > innerHeight ? r.width : r.height })()")
        p0 = sz()
        if not 44 <= p0 <= 60: bad.append(f"{tag}: sheet peek is {p0:.0f}px")
        pg.tap("#cwSheetBtn"); pg.wait_for_timeout(300); p1 = sz()
        pg.tap("#cwSheetBtn"); pg.wait_for_timeout(300); p2 = sz()
        if not p0 < p1 < p2: bad.append(f"{tag}: sheet sizes not increasing {p0:.0f}/{p1:.0f}/{p2:.0f}")
        if pg.get_attribute("#cwSheetBtn", "aria-expanded") != "true": bad.append(f"{tag}: aria-expanded not set")
        if SHOT and w == 390: pg.screenshot(path=os.path.join(SHOT, f"cad_phone_{tag}_sheet_full.png"))
        tb = pg.locator("#cwSheetBtn").bounding_box()
        x0, y0 = tb["x"] + tb["width"] / 2, tb["y"] + tb["height"] / 2
        drag(pg, x0, y0, *((x0, h - 4) if w < h else (w - 4, y0))); pg.wait_for_timeout(300)
        if pg.get_attribute("#cwSide", "data-sheet") != "peek": bad.append(f"{tag}: dragging the sheet closed left it {pg.get_attribute('#cwSide', 'data-sheet')}")
        # tapping a tab from peek opens it to half
        pg.tap("#tabHist"); pg.wait_for_timeout(250)
        if pg.get_attribute("#cwSide", "data-sheet") != "half": bad.append(f"{tag}: tab tap did not open the sheet")
        # a tool panel opens without the floats landing on the cube or each other
        pg.tap("#cwSheetBtn"); pg.wait_for_timeout(250); pg.tap("#cwSheetBtn"); pg.wait_for_timeout(250)
        if pg.get_attribute("#cwSide", "data-sheet") != "peek": bad.append(f"{tag}: handle tap from full did not return to peek")
        pg.locator("[data-tool=shapes]").click(); pg.wait_for_timeout(400)
        g3 = pg.evaluate(GEOM); tool = pg.evaluate("(() => { const r = document.querySelector('#cwTool').getBoundingClientRect(); return {x:r.left,y:r.top,r:r.right,b:r.bottom} })()")
        for a in ("rail", "quick"):
            if ov(g3[a], g3["cube"]): bad.append(f"{tag}: with a panel open {a} overlaps the cube")
            if ov(g3[a], tool) and pg.is_visible("#cwTool"): bad.append(f"{tag}: {a} covers the tool panel " + str(pg.evaluate("[...document.querySelectorAll('.zws-p')].map(e=>[e.id,e.dataset.edge,e.dataset.crowded,...Object.values(e.getBoundingClientRect().toJSON()).slice(0,4).map(Math.round)])")))
        if SHOT and w in (390, 568): pg.screenshot(path=os.path.join(SHOT, f"cad_phone_{tag}_panel.png"))
        if errs: bad.append(f"{tag}: page errors {errs[:2]}")
        c.close()
    # desktop keeps its full header: no phone mode, no '…'
    c = br.new_context(viewport={"width": 1280, "height": 800}); pg = c.new_page(); pg.goto(U + "/static/cad.html"); pg.wait_for_timeout(600)
    if pg.evaluate("document.body.classList.contains('cw-phone')") or pg.is_visible("#cwMore") or not pg.is_visible("#cwExport"): bad.append("desktop: phone layout leaked")
    c.close(); br.close()
print("\n".join(bad) or "OK"); sys.exit(1 if bad else 0)
