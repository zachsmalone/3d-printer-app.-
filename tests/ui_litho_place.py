"""Lithophane placement editor: heart before / after moving.  python tests/ui_litho_place.py URL [SHOTDIR]"""
import os, sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1].rstrip("/"); SHOTS = sys.argv[2] if len(sys.argv) > 2 else "/workspace/ui-shots/litho-crop"
os.makedirs(SHOTS, exist_ok=True); bad = []
def ok(n, c):
    print(("PASS " if c else "FAIL ") + n); c or bad.append(n)
with sync_playwright() as p:
    b = p.chromium.launch()
    for name, vp, kw in (("desktop", {"width": 1366, "height": 900}, {}), ("iphone", {"width": 390, "height": 844}, {"has_touch": True, "is_mobile": True, "device_scale_factor": 3})):
        pg = b.new_page(viewport=vp, **kw); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script("localStorage.level='expert'")
        pg.goto(URL + "/#studio"); pg.wait_for_timeout(1200)
        pg.click("#sSample"); pg.wait_for_timeout(800)
        pg.click("[data-shape='heart']"); pg.wait_for_timeout(400)
        ok(f"{name}: editor visible for heart", pg.is_visible("#lpCanvas"))
        ed = pg.locator("#placeEditor"); ed.scroll_into_view_if_needed()
        ed.screenshot(path=f"{SHOTS}/heart-before-{name}.png")
        cv = pg.locator("#lpCanvas"); bb = cv.bounding_box()
        pg.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2); pg.mouse.down()
        pg.mouse.move(bb["x"] + bb["width"] * 0.7, bb["y"] + bb["height"] * 0.4, steps=8); pg.mouse.up()
        cv.focus(); pg.keyboard.press("+"); pg.keyboard.press("+"); pg.keyboard.press("ArrowDown")
        pg.wait_for_timeout(300)
        lbl = cv.get_attribute("aria-label") or ""
        ok(f"{name}: drag + keys moved/zoomed ({lbl})", "0% across" not in lbl and "zoom 121%" in lbl)
        ed.screenshot(path=f"{SHOTS}/heart-after-{name}.png")
        pg.click("#lpReset"); ok(f"{name}: reset", "zoom 100%" in (cv.get_attribute("aria-label") or ""))
        pg.click("[data-shape='cup']"); pg.wait_for_timeout(300); ed.screenshot(path=f"{SHOTS}/cup-{name}.png")
        pg.click("[data-shape='rect']"); ok(f"{name}: hidden for rectangle", not pg.is_visible("#lpCanvas"))
        ok(f"{name}: no page errors {errs}", not errs)
    b.close()
sys.exit(1 if bad else 0)
