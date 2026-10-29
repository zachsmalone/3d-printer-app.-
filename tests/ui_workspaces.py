"""Floating workspaces in Chromium, desktop 1280x800 and phone 390x844: in Studio, Lithophane, FDM Slicer, TorchC0 and
CAD the 3D view is the full background and every panel floats over it without overlapping another panel;
Customise workspace lists every panel (core ones can't be hidden); hide/show and a dock move survive a reload;
The Customise dialog has no Reset layout button.   python tests/ui_workspaces.py URL [SHOTDIR]"""
import os, sys, tempfile
import trimesh
from playwright.sync_api import sync_playwright
U = sys.argv[1].rstrip("/"); SHOT = sys.argv[2] if len(sys.argv) > 2 else None
bad = []
def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c: bad.append(n)
STL = os.path.join(tempfile.mkdtemp(), "ws_box.stl"); trimesh.creation.box(extents=(20, 20, 10)).export(STL)
GEOM = """([root, bg]) => { const r = document.querySelector(root), v = document.querySelector(bg);
  const R = e => { const b = e.getBoundingClientRect(); return {x:b.left, y:b.top, r:b.right, b:b.bottom, w:b.width, h:b.height} };
  const ps = [...r.querySelectorAll(':scope > .zws-p')].filter(e => !e.hidden).map(e => [e.id, R(e)]);
  return {root: R(r), bg: v ? R(v) : null, ps, ids: [...r.querySelectorAll(':scope > .zws-p')].map(e => e.id)} }"""
def ov(a, b): return a["x"] < b["r"] - 1 and b["x"] < a["r"] - 1 and a["y"] < b["b"] - 1 and b["y"] < a["b"] - 1
def check_geom(pg, tag, root, bg, sheet=0):
    g = pg.evaluate(GEOM, [root, bg])
    ok(f"{tag}: the 3D view fills the workspace", g["bg"] and g["bg"]["w"] >= g["root"]["w"] - 2 and g["bg"]["h"] >= g["root"]["h"] - 2 - sheet, g)
    ok(f"{tag}: panels float over it", len(g["ps"]) >= 2, g["ids"])
    lap = [(a[0], b[0]) for i, a in enumerate(g["ps"]) for b in g["ps"][i + 1:] if ov(a[1], b[1])]
    ok(f"{tag}: no panel overlaps another", not lap, lap)
    out = [p[0] for p in g["ps"] if p[1]["x"] < g["root"]["x"] - 1 or p[1]["r"] > g["root"]["r"] + 1 or p[1]["y"] < g["root"]["y"] - 1 or p[1]["b"] > g["root"]["b"] + 1]
    ok(f"{tag}: every panel is inside the workspace", not out, out)
    pg.wait_for_timeout(1500)
    n = pg.evaluate("""r => new Promise(ok => { let n = 0; const el = document.querySelector(r), f = () => n++;
      el.addEventListener('zws:layout', f); setTimeout(() => { el.removeEventListener('zws:layout', f); ok(n) }, 1000) })""", root)
    ok(f"{tag}: layout is idle when nothing changes (render on demand)", n <= 1, n)
    return g
def customise(pg, tag, ws, root, open_model, bg, key=None):
    key = key or ws
    """hide/show persists, core can't be hidden, dock moves persist, reset restores"""
    pg.click(f"#zwsCust-{ws}"); dlg = f"#zwsDlg-{ws}"; pg.wait_for_selector(dlg + "[open]")
    boxes = pg.eval_on_selector_all(dlg + " input[data-zws]", "e => e.map(x => [x.dataset.zws, x.checked, x.disabled])")
    ok(f"{tag}: Customise lists every panel", sorted(b[0] for b in boxes) == sorted(i[4:] for i in pg.evaluate(GEOM, [root, bg])["ids"]), boxes)
    core = [b[0] for b in boxes if b[2]]; free = [b[0] for b in boxes if not b[2]]
    ok(f"{tag}: core panels are locked on", core and all(b[1] for b in boxes if b[2]), boxes)
    ok(f"{tag}: core panel refuses to hide", pg.evaluate("([w, id]) => ZWS.all[w].setHidden(id, true) === false && !ZWS.all[w].state()[id].hidden", [ws, core[0]]))
    ok(f"{tag}: core panels have no hide button", all(pg.locator(f"#zws-{c} .zws-hide").count() == 0 for c in core))
    vis_free = [b[0] for b in boxes if not b[2] and b[1]]
    if vis_free:
        h = vis_free[0]; pg.uncheck(f"{dlg} input[data-zws={h}]"); pg.wait_for_timeout(200)
        ok(f"{tag}: unticking hides {h}", pg.is_hidden(f"#zws-{h}"))
        keys = pg.evaluate("Object.keys(localStorage)")
        ok(f"{tag}: layout saved under its own workspace key", any(k.startswith("zeim.ws.") and k.split(".")[3] == key for k in keys), keys)
    pg.keyboard.press("Escape")
    # dock move: Enter on the grip sends a core panel to the next side
    e0 = pg.get_attribute(f"#zws-{core[0]}", "data-edge")
    pg.focus(f"#zws-{core[0]} .zws-grip"); pg.keyboard.press("Enter"); pg.wait_for_timeout(250)
    e1 = pg.get_attribute(f"#zws-{core[0]}", "data-edge")
    ok(f"{tag}: grip moves {core[0]} to another side", e1 != e0, (e0, e1))
    pg.reload(); open_model(); pg.wait_for_timeout(500)
    if vis_free: ok(f"{tag}: hidden {vis_free[0]} stays hidden after reload", pg.is_hidden(f"#zws-{vis_free[0]}") and pg.locator(f"#zws-{vis_free[0]}").count() == 1)
    st = pg.evaluate("w => ZWS.all[w].state()", ws)
    ok(f"{tag}: dock move remembered after reload", st[core[0]]["edge"] == e1, (st[core[0]], e1))
    if vis_free:   # show it again from Customise
        pg.click(f"#zwsCust-{ws}"); pg.check(f"{dlg} input[data-zws={vis_free[0]}]"); pg.wait_for_timeout(200)
        ok(f"{tag}: ticking shows {vis_free[0]} again", not pg.evaluate("([w, id]) => ZWS.all[w].state()[id].hidden", [ws, vis_free[0]])
           and (pg.is_visible(f"#zws-{vis_free[0]}") or pg.evaluate(f"document.querySelector('#zws-{vis_free[0]} > .zws-body > *').hidden"))); pg.keyboard.press("Escape")
        pg.click(f"#zwsCust-{ws}"); pg.uncheck(f"{dlg} input[data-zws={vis_free[0]}]")
    else: pg.click(f"#zwsCust-{ws}")
    ok(f"{tag}: Customise has no Reset layout button", pg.locator(f"{dlg} [data-zws-reset]").count() == 0 and "Reset layout" not in (pg.text_content(dlg) or ""))
    pg.keyboard.press("Escape")
    ok(f"{tag}: Customise stays reachable", pg.is_visible(f"#zwsCust-{ws}") or pg.locator("#cwMore").is_visible())
with sync_playwright() as p:
    br = p.chromium.launch()
    for w, h, m in ((1280, 800, False), (390, 844, True)):
        sz = f"{w}x{h}"
        c = br.new_context(viewport={"width": w, "height": h}, has_touch=m, is_mobile=m); pg = c.new_page()
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        # Studio / Lithophane (the sample is a lithophane)
        def studio():
            pg.wait_for_selector("#sSample", timeout=20000); pg.click("#sSample"); pg.wait_for_selector("#result:not([hidden])", state="attached", timeout=90000); pg.wait_for_timeout(800)
        pg.goto(U + "/#studio"); studio()
        pg.evaluate("localStorage.clear()"); pg.reload(); studio()
        ws_key = pg.evaluate("""() => {
          var raw = (location.hash || "").replace(/^#/, "").split(/[/?]/)[0];
          return raw === "lithophane" ? "litho" : "studio";
        }""")
        g = check_geom(pg, f"{sz} {ws_key}", "#viewCreate", "#viewer")
        if SHOT: pg.screenshot(path=os.path.join(SHOT, f"ws_{ws_key}_{sz}.png"))
        ok(f"{sz} {ws_key}: Send or save and Print are on screen", pg.is_visible("#btnSendSheet") or pg.is_visible("#zws-result .zws-chip"))
        customise(pg, f"{sz} {ws_key}", "studio", "#viewCreate", studio, "#viewer", ws_key)
        # FDM Slicer
        def slicer():
            pg.wait_for_selector("#editFile", state="attached", timeout=20000); pg.set_input_files("#editFile", STL); pg.wait_for_selector("#editResult:not([hidden])", state="attached", timeout=90000); pg.wait_for_timeout(800)
        pg.goto(U + "/#slicer"); slicer()
        check_geom(pg, f"{sz} slicer", "#viewEdit", "#editViewer")
        if SHOT: pg.screenshot(path=os.path.join(SHOT, f"ws_slicer_{sz}.png"))
        customise(pg, f"{sz} slicer", "slicer", "#viewEdit", slicer, "#editViewer")
        # TorchC0
        def torch():
            pg.wait_for_selector("#rzGo", timeout=20000); pg.set_input_files("#rzFile", STL); pg.click("#rzGo"); pg.wait_for_selector("#rzView", state="attached", timeout=200000); pg.wait_for_timeout(1200)
        pg.goto(U + "/#torchc0"); torch()
        check_geom(pg, f"{sz} torchc0", "#viewTorch", "#viewTorch > #rzView")
        if SHOT: pg.screenshot(path=os.path.join(SHOT, f"ws_torchc0_{sz}.png"))
        ok(f"{sz} torchc0: downloads still reachable", pg.locator("#torchOut a[href$='torchc0.stl']").count() == 1)
        customise(pg, f"{sz} torchc0", "torchc0", "#viewTorch", torch, "#viewTorch > #rzView")
        # CAD
        def cad(): pg.wait_for_selector("#zws-tools", timeout=20000); pg.wait_for_timeout(500)
        pg.goto(U + "/static/cad.html"); cad()
        check_geom(pg, f"{sz} cad", ".cw-main", "#cwStage", 60 if m else 0)   # phones keep the 48px History/Items sheet handle
        if m:   # on phones Customise lives in the '…' menu
            pg.tap("#cwMore"); ok(f"{sz} cad: '…' menu has Customise workspace", pg.locator("#cwMoreMenu .cw-mi", has_text="Customise workspace").count() == 1)
            pg.locator("#cwMoreMenu .cw-mi", has_text="Customise workspace").click(); pg.wait_for_selector("#zwsDlg-cad[open]"); pg.keyboard.press("Escape")
        else: customise(pg, f"{sz} cad", "cad", ".cw-main", cad, "#cwStage")
        ok(f"{sz}: no page errors", not errs, errs[:3])
        c.close()
    br.close()
print("\n".join(["FAILED:"] + bad) if bad else "ALL PASS"); sys.exit(1 if bad else 0)
