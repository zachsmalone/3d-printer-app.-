"""Headless Chrome regression for Ren Ishikawa's Batch-1 QA findings (QA-1..QA-5) plus the Edit drop zone at the 5-build cap.
python tests/ui_qa.py URL   (a TEMP-data server in PHOTO3D_MODE=local). Phone context 390x844, emulated touch. NOT a real iPhone."""
import os, sys, tempfile
from playwright.sync_api import sync_playwright
URL = sys.argv[1]
R = []
def ok(n, c, x=""): R.append(bool(c)); print(("PASS " if c else "FAIL ") + n, x)
def up(pg, sel, ack, f):
    """CR-5: an uploaded photo needs the permission box ticked first."""
    if not pg.is_checked(ack): pg.check(ack)
    pg.set_input_files(sel, f)
T = tempfile.mkdtemp()
open(T + "/fake.jpg", "wb").write(b"this is not a jpeg" * 20)
open(T + "/empty.jpg", "wb").close()
open(T + "/big.jpg", "wb").write(b"\xff\xd8\xff" + b"0" * (26 * 1024 * 1024))
J = "{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(%s)}"
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
    ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True, device_scale_factor=2)
    pg = ctx.new_page(); pg.goto(URL.rstrip("/") + "/#studio"); pg.wait_for_timeout(700)
    # ---- QA-1 (Studio -> Edit -> Studio, and back)
    pg.click("#sSample"); pg.wait_for_selector("#result:not([hidden])", timeout=120000); pg.wait_for_timeout(500)
    pg.click("#mainNav [data-view=slicer]"); pg.click("#editSample"); pg.wait_for_selector("#editResult:not([hidden])", timeout=60000); pg.wait_for_timeout(500)
    pg.click("#mainNav [data-view=lithophane]"); pg.wait_for_timeout(300)
    pg.click("#btnPrint"); pg.wait_for_selector("#dlgPrint[open]"); w = pg.inner_text("#printWhich")
    ok("QA-1: Studio Print shows the Studio lithophane, not the Edit vase", "Lithophane" in w and "Sample vase" not in w, w)
    pg.keyboard.press("Escape")
    pg.click("#mainNav [data-view=slicer]"); pg.wait_for_timeout(300)
    pg.click("#editPrint"); pg.wait_for_selector("#dlgPrint[open]"); w2 = pg.inner_text("#printWhich")
    ok("QA-1: Edit Print shows the Edit project", "Sample vase" in w2, w2)
    pg.keyboard.press("Escape")
    pg.click("#editSend"); pg.wait_for_selector("#dlgSendSheet[open]"); w3 = pg.inner_text("#ssWhich")
    ok("QA-1: Edit Send names the Edit project", "Sample vase" in w3, w3); pg.keyboard.press("Escape")
    pg.click("#mainNav [data-view=lithophane]"); pg.evaluate("location.hash=\'studio\'"); pg.click("#btnSendSheet"); pg.wait_for_selector("#dlgSendSheet[open]")
    ok("QA-1: Studio Send names the Studio build", "Sample photo" in pg.inner_text("#ssWhich"), pg.inner_text("#ssWhich")); pg.keyboard.press("Escape")
    # ---- QA-4: the finished model is brought into view after a Beginner build
    pg.reload(); pg.wait_for_timeout(600)
    pg.click("#sSample"); pg.wait_for_selector("#result:not([hidden])", timeout=120000); pg.wait_for_timeout(3500)
    top = pg.evaluate("document.querySelector('#viewer').getBoundingClientRect().top")
    tb = pg.evaluate("document.querySelector('.topbar').offsetHeight")
    ok("QA-4: after the build the viewer is on screen, below the top bar (phone)", tb - 3 <= top < 400, f"top={top} bar={tb}")
    ok("QA-4: focus + status say the model is ready", pg.evaluate("document.activeElement.id") == "resultH" and "ready" in pg.inner_text("#buildHint"))
    # ---- QA-2: refused photo is forgotten
    pg.reload(); pg.wait_for_timeout(600)
    pg.select_option("#modeSel", "expert")
    up(pg, "#sFile", "#sAck", T + "/fake.jpg"); pg.wait_for_timeout(400)
    pg.click("#btnBuild"); pg.wait_for_selector("#sMsg:not([hidden])", timeout=60000); pg.wait_for_timeout(500)
    ok("QA-2: refused photo -> inline message, no check-mark row, Build disabled", "couldn't open" in pg.inner_text("#sMsg") and not pg.is_visible("#photoChosen") and pg.is_disabled("#btnBuild"), pg.inner_text("#sMsg"))
    ok("QA-2: drop zone is empty again (no 'Photo ready')", "Photo ready" not in pg.inner_text("#drop"))
    # ---- QA-5: Expert Build is fixed to the screen at any scroll; Beginner has no floating bar over the Style cards
    pg.click("#sSample"); pg.wait_for_timeout(500)
    pos = pg.evaluate("getComputedStyle(document.querySelector('#btnBuild')).position")
    pg.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)"); pg.wait_for_timeout(300)
    r = pg.evaluate("(()=>{const b=document.querySelector('#btnBuild').getBoundingClientRect();return [b.top,b.bottom,innerHeight]})()")
    ok("QA-5: Expert Build stays on screen at the bottom of the page", pos == "fixed" and 0 < r[0] and r[1] <= r[2] + 1, f"{pos} {r}")
    pg.evaluate("window.scrollTo(0,0)"); pg.select_option("#modeSel", "beginner"); pg.wait_for_timeout(300)
    ok("QA-5: Beginner Build is not floating over the Style cards", pg.evaluate("getComputedStyle(document.querySelector('#btnBuild')).position") != "fixed")
    # ---- QA-3: Edit photo errors are inline
    pg.click("#mainNav [data-view=slicer]"); pg.wait_for_timeout(300)
    for f, want in (("empty.jpg", "couldn't open"), ("big.jpg", "over 25 MB")):
        up(pg, "#eFile", "#eAck", T + "/" + f); pg.wait_for_timeout(600)
        ok(f"QA-3: Edit {f} -> inline message under the photo buttons", want in pg.inner_text("#eMsg") and pg.locator(".toast").count() == 0, pg.inner_text("#eMsg"))
    up(pg, "#eFile", "#eAck", T + "/fake.jpg"); pg.wait_for_timeout(1500)
    ok("QA-3: Edit unreadable photo -> inline too", "couldn't open" in pg.inner_text("#eMsg"), pg.inner_text("#eMsg"))
    ctx.close()
    # ---- Edit drop zone at the 5-build cap (item 6)
    ctx = b.new_context(viewport={"width": 1100, "height": 900}); pg = ctx.new_page(); pg.goto(URL.rstrip("/") + "/#studio"); pg.wait_for_timeout(600)
    n = pg.evaluate("""async () => { const sb = await (await fetch('/static/sample.png')).blob(); let ok = 0;
        for (let i = 0; i < 5; i++) { const fd = new FormData(); fd.append('file', new File([sb], 'a'+i+'.png', {type:'image/png'})); fd.append('mode','relief'); fd.append('resolution','40'); fd.append('width_mm','40');
          fd.append('photo_ack','true'); const r = await fetch('/api/generate', {method:'POST', body: fd}); if (r.ok) { ok++; const id = (await r.json()).id;
            await fetch('/api/builds/' + id + '/favorite', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({favorite:true})}); } } return ok; }""")
    pg.reload(); pg.wait_for_timeout(800)
    pg.click("#mainNav [data-view=slicer]"); pg.wait_for_timeout(300)
    pg.click("#editSample"); pg.wait_for_selector("#dlgFull[open]", timeout=15000)
    ok("Edit at 5/5: model sample opens the 'history full' dialog (not a raw error)", n == 5 and pg.is_visible("#dlgFull"), n)
    pg.keyboard.press("Escape")
    pg.evaluate("""async () => { const stl = await (await fetch('/static/sample_model.stl')).blob(); const dt = new DataTransfer(); dt.items.add(new File([stl], 'x.stl')); document.querySelector('#editDrop').dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true})); }""")
    pg.wait_for_timeout(1500)
    ok("Edit at 5/5: dropping a file on the drop zone also gets the friendly answer (dialog, or an inline 'full' message)", pg.is_visible("#dlgFull") or "full" in pg.inner_text("#eMsg").lower() or "starred" in pg.inner_text("#eMsg").lower())
    ok("Edit at 5/5 (all starred): the dialog says so and offers no 'auto-delete oldest'", "starred" in pg.inner_text("#fullMsg") and not pg.is_visible("#btnAutoDel") if pg.is_visible("#dlgFull") else True)
    pg.keyboard.press("Escape"); pg.click("#btnAutoDel") if pg.is_visible("#btnAutoDel") else None
    ctx.close(); b.close()
import shutil; shutil.rmtree(T, ignore_errors=True)
sys.exit(0 if all(R) else 1)
