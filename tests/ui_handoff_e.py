"""E / Task 1 in a real browser: Studio Save work | Send to Slicer/TorchC0 | Send to CAD; Send to… on Slicer/TorchC0;
is visible on the Slicer; Back from CAD reopens the Studio model; TorchC0 keeps its file across leave/reload;
Print → Open in TorchC0 carries the model; photo tip hook for select mode. python tests/ui_handoff_e.py URL"""
import io, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
U = sys.argv[1].rstrip("/"); bad = []; n = 0
SHOTS = Path("/workspace/qa/task1-handoff"); SHOTS.mkdir(parents=True, exist_ok=True)
VASE = Path(__file__).resolve().parent / "fixtures" / "sample_vase.stl"
def ok(name, cond):
    global n; n += 1
    if not cond: bad.append(name)
    print(("ok  " if cond else "BAD ") + name)
def build(pg):
    from PIL import Image
    b = io.BytesIO(); Image.new("RGB", (64, 48), (120, 90, 60)).save(b, "PNG")
    r = pg.request.post(U + "/api/generate", multipart={"file": {"name": "s.png", "mimeType": "image/png", "buffer": b.getvalue()},
                        "mode": "relief", "width_mm": "50", "resolution": "40", "photo_ack": "true", "title": "Desk lamp"})
    assert r.ok, r.text(); return r.json()["id"]
def kind(pg, k):
    pg.evaluate("k => { localStorage.setItem('zeim.printKind', k); localStorage.setItem('zeim.printKindNoteOff','1'); }", k)
def open_build(pg, bid):
    pg.evaluate("id => document.dispatchEvent(new CustomEvent('zeim:open-build', { detail: id }))", bid)
    pg.wait_for_function("id => window.__photo3d?.current?.id === id", arg=bid, timeout=15000)
with sync_playwright() as p:
    br = p.chromium.launch()
    # Age gate: server may run with PHOTO3D_AGE_GATE=0; also set the remembered answer.
    for tag, vp in (("desktop", {"width": 1280, "height": 860}), ("phone", {"width": 390, "height": 844})):
        ctx = br.new_context(viewport=vp, has_touch=tag == "phone", is_mobile=tag == "phone")
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script("try { localStorage.setItem('zeim.adult','yes'); } catch (e) {}")
        pg.goto(U + "/#studio"); kind(pg, "fdm"); pg.reload(); pg.wait_for_timeout(1500)
        pg.evaluate("""() => { const g=document.getElementById('ageGate'); if(g)g.remove(); document.documentElement.classList.remove('gated'); }""")
        bid = build(pg); open_build(pg, bid)
        ok(f"{tag}: Studio handoff row visible", pg.is_visible("#studioHandoff") and pg.is_visible("#btnSaveWork") and pg.is_visible("#btnSendSlicer") and pg.is_visible("#btnSendCad"))
        bbs = [pg.locator(s).bounding_box() for s in ("#btnSaveWork", "#btnSendSlicer", "#btnSendCad")]
        ok(f"{tag}: three handoff buttons side by side and tappable", all(b and b["height"] >= 44 for b in bbs) and max(b["y"] for b in bbs) - min(b["y"] for b in bbs) < 4 and bbs[2]["x"] > bbs[0]["x"])
        pg.screenshot(path=str(SHOTS / f"{tag}_studio_handoff.png"))
        pg.click("#btnSendSlicer")
        pg.wait_for_function("() => window.__zeimEdit?.p?.id", timeout=30000); pg.wait_for_timeout(800)
        ok(f"{tag}: Slicer opened with the model", pg.evaluate("location.hash") == "#slicer" and bool(pg.evaluate("__zeimEdit.p.id")))
        # Phone folds the Slicer result panel; wait for the inline button or the floating stand-in.
        try:
            pg.wait_for_function("""() => {
              const i = document.querySelector('#editSendTo');
              if (i && i.offsetParent && i.getClientRects().length) return true;
              const f = document.querySelector('#sendToFab');
              return !!(f && !f.hidden && f.getClientRects().length);
            }""", timeout=5000)
        except Exception:
            pass
        sb = "#editSendTo" if pg.is_visible("#editSendTo") else "#sendToFab"
        ok(f"{tag}: Slicer Send to… visible (limit 1; {sb})", pg.is_visible(sb))
        bb = pg.locator(sb).bounding_box()
        ok(f"{tag}: Slicer Send to… in the viewport-width, tappable", bb and bb["height"] >= 44 and bb["x"] >= 0 and bb["x"] + bb["width"] <= vp["width"] + 1)
        ok(f"{tag}: Back to Studio chip", pg.is_visible("#backChip") and "Studio" in pg.text_content("#backChip"))
        pg.click(sb); pg.wait_for_selector("#dlgSendTo[open]")
        ok(f"{tag}: Slicer menu offers CAD only for FDM", pg.eval_on_selector_all("#dlgSendTo [data-to]", "bs => bs.map(b => b.dataset.to)") == ["cad"])
        pg.keyboard.press("Escape"); pg.screenshot(path=str(SHOTS / f"{tag}_slicer_sendto.png"))
        # Studio → CAD → back: Studio model kept (limit 2)
        pg.goto(U + "/#studio"); pg.wait_for_timeout(1500); open_build(pg, bid)
        pg.click("#btnSendCad"); pg.wait_for_url("**/static/cad.html**", timeout=30000); pg.wait_for_timeout(2500)
        ok(f"{tag}: CAD got the model", bool(pg.evaluate("window.__cad?.S?.bid")))
        ok(f"{tag}: CAD Back to Studio chip", pg.is_visible("#backChip") and "Studio" in pg.text_content("#backChip"))
        ok(f"{tag}: CAD Send to menu (FDM shows Slicer only)", pg.evaluate("!document.querySelector('#cwSendSlicer').hidden && document.querySelector('#cwSendTorch').hidden"))
        pg.screenshot(path=str(SHOTS / f"{tag}_cad_back.png"))
        pg.click("#backChip"); pg.wait_for_url("**/#lithophane", timeout=15000)
        try: pg.wait_for_function("id => window.__photo3d?.current?.id === id", arg=bid, timeout=15000); got = True
        except Exception: got = False
        ok(f"{tag}: Back from CAD reopens the Studio model (limit 2)", got and pg.is_visible("#result"))
        pg.screenshot(path=str(SHOTS / f"{tag}_studio_back.png"))
        # resin: Studio → TorchC0, file kept across leave + reload (limit 3)
        kind(pg, "resin"); pg.reload(); pg.wait_for_timeout(1500); open_build(pg, bid)
        ok(f"{tag}: Resin middle button is Send to TorchC0", "TorchC0" in (pg.text_content("#btnSendSlicer") or ""))
        pg.click("#btnSendSlicer")
        pg.wait_for_function("() => document.querySelector('#rzFile')?.files?.length === 1", timeout=20000)
        ok(f"{tag}: TorchC0 got the file", pg.evaluate("document.querySelector('#rzFile').files[0].name") == "studio.stl")
        pg.goto(U + "/#showcase"); pg.wait_for_timeout(800); pg.goto(U + "/#torchc0"); pg.reload(); pg.wait_for_timeout(500)
        try: pg.wait_for_function("() => document.querySelector('#rzFile')?.files?.length === 1", timeout=15000); kept = True
        except Exception: kept = False
        ok(f"{tag}: TorchC0 keeps the file after leaving + reload (limit 3)", kept and "kept from before" in pg.text_content("#rzFileStatus"))
        ok(f"{tag}: TorchC0 Send to… visible", pg.is_visible("#torchSendTo"))
        pg.screenshot(path=str(SHOTS / f"{tag}_torchc0_kept.png"))
        # TorchC0: a picked file replaces the kept one
        pg.set_input_files("#rzFile", str(VASE)); pg.wait_for_timeout(600); pg.reload()
        pg.wait_for_function("() => document.querySelector('#rzFile')?.files?.length === 1", timeout=15000)
        ok(f"{tag}: newly picked file is the one kept", pg.evaluate("document.querySelector('#rzFile').files[0].name") == "sample_vase.stl")
        # B's Print → Open in TorchC0 carries the model
        pg.evaluate("() => indexedDB.deleteDatabase('zeim-handoff')"); pg.goto(U + "/#studio"); pg.reload(); pg.wait_for_timeout(1500); open_build(pg, bid)
        pg.evaluate("() => { const d = document.querySelector('#dlgPrint'); d.showModal(); }")
        pg.evaluate("() => document.querySelector('#printToTorch').click()")
        try: pg.wait_for_function("() => document.querySelector('#rzFile')?.files?.[0]?.name === 'studio.stl'", timeout=20000); carried = True
        except Exception: carried = False
        ok(f"{tag}: Print → Open in TorchC0 carries the model", carried and pg.evaluate("location.hash") == "#torchc0" and not pg.evaluate("document.querySelector('#dlgPrint').open"))
        # select mode photo tip hook (selectmode.js lives on another branch: simulate its panel)
        pg.evaluate("""() => { const p = document.createElement('div'); p.id = 'selPanel'; p.innerHTML = '<p id="selSay">Draw round</p>'; document.body.append(p);
                        document.dispatchEvent(new CustomEvent('zeim:file')); }""")
        ok(f"{tag}: photo tip added under select mode's first line", pg.evaluate("document.querySelector('#selSay').nextElementSibling?.classList.contains('phototips')"))
        noise = [e for e in errs if "createObjectURL" not in e]; ok(f"{tag}: no page errors ({noise[:2]})", not noise)
        ctx.close()
    br.close()
print(f"{n - len(bad)}/{n} passed"); sys.exit(1 if bad else 0)
