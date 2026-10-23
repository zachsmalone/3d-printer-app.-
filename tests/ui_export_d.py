"""D in a real browser: export picker (formats + one-line descriptions, remembered per workspace, one-tap rename,
safe names, real download), Saving your work (where saved, auto/remind/off, 2/5/10), Back up all, and the gentle
iPhone-Safari note for guests. python tests/ui_export_d.py URL"""
import io, sys, zipfile
from pathlib import Path
from playwright.sync_api import sync_playwright
U = sys.argv[1].rstrip("/"); bad = []; n = 0
SHOTS = Path("/workspace/qa/prelaunch-audit/after/D"); SHOTS.mkdir(parents=True, exist_ok=True)
SAMPLE = Path(__file__).resolve().parent / "fixtures"
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
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
with sync_playwright() as p:
    br = p.chromium.launch()
    for tag, vp, ua in (("desktop", {"width": 1280, "height": 860}, None), ("phone", {"width": 390, "height": 844}, IPHONE)):
        ctx = br.new_context(viewport=vp, user_agent=ua, accept_downloads=True, has_touch=tag == "phone", is_mobile=tag == "phone")
        pg = ctx.new_page(); pg.goto(U + "/#studio"); pg.wait_for_timeout(1500)
        bid = build(pg)
        ok(f"{tag}: Studio has one Export… button", pg.locator("#studioExport").count() == 1)
        pg.evaluate("bid => zeimExport.open({ ws: 'studio', bid })", bid); pg.wait_for_selector("#dlgExport[open]")
        fm = pg.locator("#dlgExport input[name=expFmt]")
        ok(f"{tag}: six formats", fm.count() == 6)
        ok(f"{tag}: each has a one-line description", pg.locator("#dlgExport .expfmt small").count() == 6)
        ok(f"{tag}: STEP explained, not offered", "true solid" in pg.text_content("#expStep") and pg.locator("input[value=step]").count() == 0)
        nm = pg.text_content("#expNameOut")
        ok(f"{tag}: default name Title - Printer - 0.2mm ({nm})", nm.startswith("Desk lamp - ") and nm.endswith(" - 0.2mm.3mf"))
        pg.check("#dlgExport input[value=glb]"); ok(f"{tag}: name follows format", pg.text_content("#expNameOut").endswith(".glb"))
        pg.screenshot(path=str(SHOTS / f"{tag}_picker.png"))
        pg.click("#expRename"); pg.fill("#expName", 'Lamp: "final"?'); pg.screenshot(path=str(SHOTS / f"{tag}_rename.png"))
        pg.click("#expNameOk"); pg.wait_for_timeout(500)
        ok(f"{tag}: rename made safe", pg.text_content("#expNameOut") == "Lamp final.glb")
        with pg.expect_download() as d: pg.click("#expGo")
        dl = d.value; ok(f"{tag}: real GLB download named {dl.suggested_filename}", dl.suggested_filename == "Lamp final.glb" and open(dl.path(), "rb").read(4) == b"glTF")
        pg.click("#expCancel")
        pg.evaluate("bid => zeimExport.open({ ws: 'studio', bid })", bid); pg.wait_for_selector("#dlgExport[open]")
        ok(f"{tag}: last format remembered for Studio", pg.is_checked("#dlgExport input[value=glb]"))
        ok(f"{tag}: renamed name remembered", pg.text_content("#expNameOut") == "Lamp final.glb")
        pg.click("#expCancel")
        pg.evaluate("bid => zeimExport.open({ ws: 'slicer', bid })", bid); pg.wait_for_selector("#dlgExport[open]")
        ok(f"{tag}: Slicer has its own remembered format (default 3MF)", pg.is_checked("#dlgExport input[value='3mf']"))
        pg.click("#expCancel")
        # Account: saving your work + where it is saved + Back up all
        pg.goto(U + "/#account/save"); pg.wait_for_timeout(1500)
        ok(f"{tag}: where saved = this browser (guest)", "only in this browser" in pg.text_content("#saveWhere"))
        ok(f"{tag}: indicator explains where", "only in this browser" in (pg.get_attribute("#saveInd", "title") or ""))
        pg.check("input[name=saveMode][value=remind]"); pg.select_option("#saveEvery", "2"); pg.wait_for_timeout(300)
        ok(f"{tag}: reminder every 2 min saved", "Reminding you every 2 minutes" in pg.text_content("#saveStatus") and pg.evaluate("JSON.parse(localStorage['zeim.save']).every") == 2)
        pg.check("input[name=saveMode][value=off]"); pg.wait_for_timeout(200)
        ok(f"{tag}: off disables interval", pg.is_disabled("#saveEvery"))
        pg.check("input[name=saveMode][value=auto]"); pg.select_option("#saveEvery", "10")
        with pg.expect_download() as d: pg.click("#backupAll")
        z = zipfile.ZipFile(d.value.path()); ok(f"{tag}: Back up all zip uses chosen name", "Lamp final.3mf" in z.namelist())
        sn = pg.locator("#safariNote")
        if tag == "phone":
            ok("phone: iPhone Safari guest sees the 7-day note", sn.count() == 1 and "7 days" in sn.text_content())
            pg.screenshot(path=str(SHOTS / "phone_account_safari_note.png"), full_page=False)
            pg.locator("#savePrefs").scroll_into_view_if_needed(); pg.screenshot(path=str(SHOTS / "phone_account_saving.png"))
            pg.click("#safariNote [data-s=x]"); pg.reload(); pg.wait_for_timeout(1200)
            ok("phone: note stays dismissed", pg.locator("#safariNote").count() == 0)
            ok("phone: no horizontal scroll", not pg.evaluate("document.documentElement.scrollWidth > innerWidth + 1"))
        else:
            ok("desktop: no Safari note on Chrome desktop", sn.count() == 0)
            pg.locator("#savePrefs").scroll_into_view_if_needed(); pg.screenshot(path=str(SHOTS / "desktop_account_saving.png"))
            # signed in: on your account
            r = pg.request.post(U + "/api/me/signup", data={"display_name": "Ada Adult", "dob": "1985-05-05"})
            pg.reload(); pg.wait_for_timeout(1500)
            ok("desktop: signed in = on your account", r.ok and "on your account" in pg.text_content("#saveWhere"))
            # CAD workspace: one picker item in Export menu
            pg.goto(U + "/static/cad.html"); pg.wait_for_timeout(2500)
            ok("desktop: CAD Export menu has the picker", pg.locator("#cwPick").count() == 1 and pg.locator("#cwDl3mf").is_hidden())
            ok("desktop: CAD has save indicator", pg.locator("#saveInd").count() == 1)
        ctx.close()
    br.close()
print(f"{n - len(bad)}/{n} ok"); sys.exit(1 if bad else 0)
