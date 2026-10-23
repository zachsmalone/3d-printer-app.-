"""Headless Chromium: the first-visit 18+ gate. argv: URL (server started with PHOTO3D_AGE_GATE=1)."""
import sys
from playwright.sync_api import sync_playwright
U = sys.argv[1].rstrip("/") + "/"
R = []
def ok(n, c, x=""): R.append(bool(c)); print(("PASS " if c else "FAIL ") + n, x)
with sync_playwright() as p:
    b = p.chromium.launch()
    for vw in ({"width": 390, "height": 844}, {"width": 1280, "height": 900}):
        c = b.new_context(viewport=vw); pg = c.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(U); pg.wait_for_timeout(600)
        ok(f"{vw['width']}: gate covers the page", pg.locator("#ageGate").is_visible() and "18" in pg.inner_text("#ageGateTitle"))
        ok(f"{vw['width']}: page behind is inert", pg.evaluate("[...document.body.children].filter(e=>e.id!=='ageGate'&&e.tagName!=='SCRIPT').every(e=>e.hasAttribute('inert'))"))
        h = pg.evaluate("[...document.querySelectorAll('#ageYes,#ageNo')].map(e=>e.getBoundingClientRect().height)")
        ok(f"{vw['width']}: buttons are at least 44px", min(h) >= 44, h)
        ok(f"{vw['width']}: Yes has focus", pg.evaluate("document.activeElement.id") == "ageYes")
        pg.click("#ageNo"); pg.wait_for_timeout(200)
        ok(f"{vw['width']}: No shows a polite exit", pg.locator("#ageBye").is_visible() and pg.locator("#ageYes").is_hidden())
        ok(f"{vw['width']}: No stores nothing", pg.evaluate("localStorage.getItem('zeim.adult')") is None)
        pg.reload(); pg.wait_for_timeout(500)
        ok(f"{vw['width']}: after No, a reload asks again", pg.locator("#ageYes").is_visible())
        pg.click("#ageYes"); pg.wait_for_timeout(300)
        ok(f"{vw['width']}: Yes opens the app", pg.locator("#ageGate").count() == 0 and pg.locator("#mainNav").is_visible())
        ok(f"{vw['width']}: Yes is remembered on this device", pg.evaluate("localStorage.getItem('zeim.adult')") == "yes")
        pg.reload(); pg.wait_for_timeout(500)
        ok(f"{vw['width']}: no gate on the next visit", pg.locator("#ageGate").count() == 0)
        ok(f"{vw['width']}: no page errors", not errs, errs[:2])
        c.close()
    b.close()
print("PASS chrome" if all(R) else "FAIL some", sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
