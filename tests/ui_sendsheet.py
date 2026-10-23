"""Headless Chrome: the Send sheet (SEND-2..9). argv: URL_LOCAL (PHOTO3D_MODE=local, PHOTO3D_SEND_SHARE=1) URL_SHARED (PHOTO3D_MODE=shared).
The share sheet is STUBBED (navigator.share/canShare replaced): this proves our page logic, NOT that an iPhone accepts STL/OBJ/3MF."""
import json, os, sys
from playwright.sync_api import sync_playwright
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__))); import zws_open; zws_open.install()   # C: phone panels start as chips
LOCAL, SHARED = sys.argv[1], sys.argv[2]
R = []
def ok(n, c, x=""): R.append(bool(c)); print(("PASS " if c else "FAIL ") + n, x)
J = "{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(%s)}"
STUB = """
window.__shares = [];
window.__mode = 'ok';
navigator.canShare = (d) => !!(d && d.files && d.files.length && d.files[0].type !== 'text/plain');
navigator.share = async (d) => { window.__shares.push({keys: Object.keys(d), name: d.files && d.files[0].name, type: d.files && d.files[0].type, size: d.files && d.files[0].size});
  if (window.__mode === 'ok') return; const e = new Error('x'); e.name = window.__mode; throw e; };
"""
def sheet_text(pg): return pg.inner_text("#dlgSendSheet")
def build(pg):
    pg.click("#sSample"); pg.wait_for_timeout(300)
    if pg.locator("#btnBuild").is_enabled(): pg.click("#btnBuild")
    pg.wait_for_selector("#result:not([hidden])", timeout=120000); pg.wait_for_timeout(500)
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
    # ---------------- adult on the user's own computer (local mode) with the share flag on
    ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True, device_scale_factor=2)
    ctx.add_init_script(STUB)
    pg = ctx.new_page(); reqs = []; pg.on("request", lambda r: reqs.append(r.url)); pg.goto(LOCAL.rstrip("/") + "/#studio")
    pg.evaluate("fetch('/api/me/signup'," + J % "{display_name:'Ada Adult',dob:'1985-05-05'}" + ")"); pg.reload(); pg.wait_for_timeout(600)
    build(pg)
    ok("loose STL/OBJ/3MF buttons are gone from the result bar", pg.locator("#result .actions a[download]").count() == 0 and pg.locator("#btnSendSheet").is_visible())
    pg.evaluate("location.hash=\'studio\'"); pg.click("#btnSendSheet"); pg.wait_for_selector("#dlgSendSheet[open]"); pg.wait_for_timeout(800)
    t = sheet_text(pg)
    ok("adult sheet: title + Save + file note", "Send or save your model" in t and "Save to this device" in t and "Sending:" in t, t[:120].replace("\n", " "))
    ok("Beginner hides the chooser behind 'Different file type?'", "Different file type?" in t and not pg.locator("#ssBody > .fmt").count())
    ok("Share, Email, Shapr3D, printer rows present for an adult (stubbed share)", all(x in t for x in ("Share…", "Email it to myself", "Share as STL for Shapr3D", "Send to my printer")))
    ok("Shapr3D caption says reference + millimetres", "reference shape, not editable" in t and "millimetres" in t)
    ok("Creality is a plain link-out with rel=noopener noreferrer", pg.locator("#ssBody a[href*=crealitycloud][rel='noopener noreferrer'][target=_blank]").count() == 1 and "does not connect to Creality" in pg.text_content("#ssBody"))
    ok("save link is a generic file name", pg.get_attribute("#ssSave", "download") == "ZEIM-build.3mf" and "/files/" in pg.get_attribute("#ssSave", "href"))
    ok("photo warning (adult) + privacy line + can't-undo line", "is</b>" not in t and "is the photo" in t and "ZEIM sends nothing to other apps" in t and "copies you already sent stay where they are" in t)
    ok("targets in the sheet are >= 44px", pg.evaluate("[...document.querySelectorAll('#dlgSendSheet button,#dlgSendSheet a.btn')].filter(e=>e.offsetParent).every(e=>e.getBoundingClientRect().height>=43.5)"))
    pg.screenshot(path="previews/ui_sendsheet_adult.png")
    pg.click("#ssShare"); pg.wait_for_timeout(300)
    s = pg.evaluate("window.__shares")
    ok("share payload is {files,title} only - no url, no text", s and s[0]["keys"] == ["files", "title"], json.dumps(s))
    ok("shared file has a generic name and the real MIME fallback", s and s[0]["name"] == "ZEIM-build.3mf" and s[0]["type"] == "model/3mf")
    ok("success copy", "Sent to the app you chose." in pg.inner_text("#ssStatus"))
    for mode, want, focus in (("AbortError", "", "ssShare"), ("NotAllowedError", "Tap Share again.", "ssShare"), ("TypeError", "That didn't work on this device. Save it instead.", "ssSave")):
        pg.evaluate(f"window.__mode='{mode}'"); pg.evaluate("document.querySelector('#ssAlert').textContent='';document.querySelector('#ssStatus').textContent=''")
        pg.click("#ssShare"); pg.wait_for_timeout(250)
        ok(f"{mode}: copy '{want}' and focus on {focus}", pg.inner_text("#ssAlert").strip() == want and pg.evaluate("document.activeElement.id") == focus, pg.inner_text("#ssAlert"))
    ok("sheet never requested a signed /f/ link", not [u for u in reqs if "/f/" in u])
    pg.evaluate("window.__mode='ok'")
    pg.click("#ssShapr"); pg.wait_for_timeout(1200)
    ok("Shapr3D row forces STL first", pg.locator("[data-fmt=stl].on, [data-fmt=stl][aria-checked=true]").count() >= 1 and "STL is chosen" in pg.inner_text("#ssAlert"))
    pg.click("#ssShapr"); pg.wait_for_timeout(300)
    ok("then shares an STL", pg.evaluate("window.__shares").pop()["name"] == "ZEIM-build.stl")
    pg.click("[data-close-sheet]"); pg.wait_for_timeout(200)
    # expert shows the chooser with sizes
    pg.select_option("#modeSel", "expert"); pg.evaluate("location.hash=\'studio\'"); pg.click("#btnSendSheet"); pg.wait_for_selector("#dlgSendSheet[open]")
    ok("Expert: chooser with 3 types and sizes", pg.locator("#ssBody .fmt button").count() == 3 and ("MB" in pg.inner_text("#ssBody .fmt") or "KB" in pg.inner_text("#ssBody .fmt")), pg.inner_text("#ssBody .fmt"))
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
    # history card Send…
    pg.select_option("#modeSel", "beginner")
    ok("history card has Send…", pg.locator("#histList [data-send]").count() >= 1)
    pg.locator("#histList [data-send]").first.click(); pg.wait_for_selector("#dlgSendSheet[open]"); ok("history Send… opens the sheet", "Send or save your model" in sheet_text(pg)); pg.keyboard.press("Escape")
    # print dialog: Send… shortcut; local mode shows the honest label and Start print unchecked
    pg.click("#btnPrint"); pg.wait_for_selector("#dlgPrint[open]"); pt = pg.inner_text("#dlgPrint")
    ok("Print dialog: local mode keeps the printer block with the honest label", pg.is_visible("#printerBlock") and "Tested with a pretend printer only" in pt and not pg.is_checked("#startNow") and "stay nearby" in pt)
    pg.click("#printToSend"); pg.wait_for_selector("#dlgSendSheet[open]"); ok("Print: 'Just need the file? Send…' opens the sheet", "Send or save your model" in sheet_text(pg)); pg.keyboard.press("Escape")
    pg.keyboard.press("Escape")
    # K1 preset in Settings: experimental label, bed 220x220, Test button disabled until saved (and it never prints)
    pg.evaluate("location.hash='account'"); pg.click("#btnSettings"); pg.wait_for_selector("#dlgSettings[open]"); pg.click("#btnAddPrinter")
    pg.select_option("#printerList [data-f=profile]", "creality_k1"); pg.wait_for_timeout(200)
    st = pg.inner_text("#printerList")
    ok("K1 preset: Experimental text + 220x220 + type Moonraker (no new type)", "Experimental" in st and pg.input_value("#printerList [data-f=bed_x]") == "220" and pg.input_value("#printerList [data-f=bed_y]") == "220" and pg.input_value("#printerList [data-f=type]") == "moonraker" and "Creality" not in pg.inner_text("#printerList [data-f=type]"))
    ok("K1 preset: honest 'pretend printer only' + Test disabled before saving", "Tested with a pretend printer only" in st and pg.is_disabled("#printerList [data-test]"))
    # Since e4b2283 the Settings sheet has no printer URL field (arbitrary printer URLs were an SSRF risk); the row says so.
    ok("no printer URL field; the row says direct control is off and why", pg.locator("#printerList [data-f=url]").count() == 0 and "Direct control is off" in st and "SSRF" in st)
    pg.click("#btnSaveSettings"); pg.wait_for_timeout(600)
    pg.evaluate("location.hash='account'"); pg.click("#btnSettings"); pg.wait_for_selector("#dlgSettings[open]"); pg.click("#printerList [data-test]"); pg.wait_for_timeout(1500)
    to = pg.inner_text("#printerList [data-testout]")
    ok("Test connection answers in plain words (no address saved, nothing contacted)", "✖" in to and "address" in to.lower(), to)
    pg.keyboard.press("Escape")
    # offline copy
    ctx.set_offline(True); pg.evaluate("window.dispatchEvent(new Event('offline'))")
    pg.evaluate("location.hash=\'studio\'"); pg.click("#btnSendSheet"); pg.wait_for_selector("#dlgSendSheet[open]"); pg.wait_for_timeout(500)
    ok("offline: honest message, Save still there", "You're offline" in pg.inner_text("#ssAlert") and pg.is_visible("#ssSave"), pg.inner_text("#ssAlert"))
    ctx.set_offline(False); pg.keyboard.press("Escape")
    # Edit has the same sheet
    pg.click("#mainNav [data-view=slicer]"); pg.wait_for_timeout(300)
    pg.click("#editSample"); pg.wait_for_selector("#editResult:not([hidden])", timeout=60000); pg.wait_for_timeout(500)
    ok("Edit: loose download buttons gone, Send is there", pg.locator("#editResult .actions a[download]").count() == 0 and pg.is_visible("#editSend"))
    pg.click("#editSend"); pg.wait_for_selector("#dlgSendSheet[open]"); et = sheet_text(pg)
    ok("Edit sheet: same rules + original file row, no photo warning", "Save to this device" in et and "Your original file" in et and "is the photo" not in et, et[:160].replace("\n", " "))
    pg.keyboard.press("Escape")
    ctx.close()
    # ---------------- shared (hosted) mode: a signed-out visitor sees Download only, no printer UI
    ctx2 = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True); ctx2.add_init_script(STUB)
    t = ctx2.new_page(); t.goto(SHARED.rstrip("/") + "/#studio")
    t.reload(); t.wait_for_timeout(600)
    build(t); t.evaluate("location.hash=\'studio\'"); t.click("#btnSendSheet"); t.wait_for_selector("#dlgSendSheet[open]"); t.wait_for_timeout(500); tt = sheet_text(t)
    ok("visitor: Save your model / Download my model only", "Save your model" in tt and "Download my model" in tt and not any(x in tt for x in ("Share…", "Email", "Shapr3D", "printer", "Creality", "file type")), tt[:200].replace("\n", " "))
    ok("visitor: account note + photo warning", "isn't available for your account" in tt and "Anyone with the file can see the picture" in tt)
    t.screenshot(path="previews/ui_sendsheet_visitor.png")
    ctx2.close()
    # hosted adult: no share row without the flag, printer block replaced by the hosted line
    ctx3 = b.new_context(viewport={"width": 1100, "height": 900}); a = ctx3.new_page(); a.goto(SHARED.rstrip("/") + "/#studio")
    a.evaluate("fetch('/api/me/signup'," + J % "{display_name:'Ada Adult',dob:'1985-05-05'}" + ")"); a.reload(); a.wait_for_timeout(600)
    build(a); a.evaluate("location.hash=\'studio\'"); a.click("#btnSendSheet"); a.wait_for_selector("#dlgSendSheet[open]"); at = sheet_text(a)
    ok("hosted adult: share rows hidden while the flag is off; fallback note shown", "Share…" not in at and "press and hold the file" in at and "Save to this device" in at)
    a.keyboard.press("Escape")
    if a.locator("#btnPrint").is_visible():
        a.click("#btnPrint"); a.wait_for_selector("#dlgPrint[open]")
        ok("hosted: printer UI not rendered, download-and-open line instead", not a.is_visible("#printerBlock") and a.is_visible("#printerHosted"))
    ctx3.close(); b.close()
sys.exit(0 if all(R) else 1)
