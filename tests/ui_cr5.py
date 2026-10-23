"""CR-5 in a real browser: the photo-permission box in Studio and Edit. python tests/ui_cr5.py URL (server with PHOTO3D_PHOTO_ACK_REQUIRED unset = on)."""
import os, sys, tempfile
from PIL import Image
from playwright.sync_api import sync_playwright
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__))); import zws_open; zws_open.install()   # C: phone panels start as chips
URL = sys.argv[1]
R = []
def ok(n, c, x=""): R.append(bool(c)); print(("PASS " if c else "FAIL ") + n, x)
T = tempfile.mkdtemp(); P = T + "/mine.png"
Image.effect_mandelbrot((96, 96), (-2, -1.5, 1, 1.5), 40).convert("RGB").save(P)
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    pg = b.new_context(viewport={"width": 390, "height": 844}).new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL.rstrip("/") + "/#studio"); pg.wait_for_selector("#mainNav"); pg.wait_for_timeout(700)
    for pre, label in (("s", "Studio"), ("e", "Edit")):
        if pre == "e": pg.click("#mainNav [data-view=slicer]"); pg.wait_for_timeout(400)
        box = f"#{pre}Ack"
        ok(f"{label}: permission box exists, is NOT pre-ticked", pg.is_visible(box) and not pg.is_checked(box))
        ok(f"{label}: wording asks for own photo/permission, no addresses, workplace names or license plates (A: 18+ wording)", all(x in pg.inner_text(f"#{pre}Pick .pp-ack") for x in ("my photo", "permission", "addresses", "workplace names", "license plates")))
        pg.set_input_files(f"#{pre}File", P); pg.wait_for_timeout(600)
        ok(f"{label}: choosing a photo without the tick is refused with a clear message", pg.is_visible(f"#{pre}Msg") and "tick the box" in pg.inner_text(f"#{pre}Msg"))
        ok(f"{label}: ...and nothing was built / opened", not pg.is_visible("#result") if pre == "s" else not pg.is_visible("#editPanel"))
        pg.check(box); pg.set_input_files(f"#{pre}File", P)
        pg.wait_for_selector("#result:not([hidden])" if pre == "s" else "#editPanel:not([hidden])", timeout=120000)
        ok(f"{label}: with the box ticked the photo is accepted", True)
        pg.reload(); pg.wait_for_selector("#mainNav"); pg.wait_for_timeout(500)
        if pre == "s": pg.click("#mainNav [data-view=slicer]"); pg.wait_for_timeout(300); pg.click("#mainNav [data-view=lithophane]"); pg.wait_for_timeout(300)
    # sample needs no tick
    pg.click("#mainNav [data-view=lithophane]"); pg.reload(); pg.wait_for_selector("#mainNav"); pg.wait_for_timeout(500)
    ok("Studio: box is unticked again after a reload", not pg.is_checked("#sAck"))
    pg.click("#sSample"); pg.wait_for_selector("#result:not([hidden])", timeout=120000)
    ok("Studio: the built-in sample image builds without ticking", True)
    pg.click("#mainNav [data-view=slicer]"); pg.wait_for_timeout(300)
    ok("Edit: box unticked", not pg.is_checked("#eAck"))
    pg.click("#eSample"); pg.wait_for_selector("#editPanel:not([hidden])", timeout=120000)
    ok("Edit: the built-in sample image opens without ticking", True)
    ok("no page errors", not errs, errs)
    b.close()
sys.exit(0 if all(R) else 1)
