"""Screenshots: blurred Mature content card + the once-per-session confirm dialog (keyboard: focus starts on Go back, Esc closes).
python tests/ui_nsfw_shots.py URL OUTDIR"""
import os, sys
from playwright.sync_api import sync_playwright
URL, OUT = sys.argv[1].rstrip("/"), sys.argv[2]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PNG = open(os.path.join(ROOT, "static", "sample.png"), "rb").read()
with sync_playwright() as p:
    b = p.chromium.launch()
    owner = b.new_context(); r = owner.request
    r.post(URL + "/api/me/signup", data={"display_name": "Ada", "dob": "1985-05-05"})
    g = r.post(URL + "/api/generate", multipart={"file": {"name": "a.png", "mimeType": "image/png", "buffer": PNG}, "mode": "relief", "photo_ack": "true"}).json()
    it = r.post(URL + "/api/showcase", data={"build_id": g["id"], "title": "Venus figure study", "description": "classical nude", "tags": [], "accept_guidelines": True, "nsfw": True, "visibility": "public"}).json()
    assert it.get("nsfw") is True, it
    ctx = b.new_context(viewport={"width": 1200, "height": 900}); pg = ctx.new_page()
    pg.goto(URL + "/#showcase"); pg.wait_for_selector("#shGrid .pcard"); pg.fill("#shSearch", "venus"); pg.press("#shSearch", "Enter")
    pg.wait_for_selector("#shGrid .pcard .mature-label"); pg.wait_for_timeout(500)
    card = pg.locator("#shGrid .pcard:has(.mature-label)").first
    card.screenshot(path=f"{OUT}/blurred_card.png"); pg.screenshot(path=f"{OUT}/showcase_grid.png")
    print("blur", pg.eval_on_selector("#shGrid .ph.nsfw img", "e => getComputedStyle(e).filter"))
    card.locator("a[data-open]").focus(); pg.keyboard.press("Enter")
    pg.wait_for_selector("#dlgMature[open]"); pg.wait_for_timeout(300)
    print("focus", pg.evaluate("document.activeElement.id"))
    pg.screenshot(path=f"{OUT}/confirm_dialog.png")
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200); print("esc closed", not pg.is_visible("#dlgMature"), "item open", pg.is_visible("#dlgItem"))
    card.locator("a[data-open]").click(); pg.wait_for_selector("#dlgMature[open]"); pg.keyboard.press("Tab"); pg.keyboard.press("Enter")
    pg.wait_for_selector("#dlgItem[open]"); pg.wait_for_timeout(500); pg.screenshot(path=f"{OUT}/item_unblurred.png")
    print("alt", pg.get_attribute("#itBody img", "alt"))
    pg.click("#dlgItem [data-close]"); card.locator("a[data-open]").click(); pg.wait_for_selector("#dlgItem[open]"); print("second open asked again", pg.is_visible("#dlgMature"))
    b.close()
