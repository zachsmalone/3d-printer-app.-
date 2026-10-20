"""Mild NSFW in a real browser (Chrome + WebKit): hidden by default; after opting in, a tagged project shows in Showcase search as a blurred card with a
"Mature content" label (not hidden), opening it asks "Are you sure?" once per visit (focus on Go back, Esc = Go back),
then it opens unblurred; "Hide mature content entirely" removes it from the feed; Publish needs the NSFW answer.
python tests/ui_nsfw.py URL"""
import os, sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1].rstrip("/"); bad = []
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PNG = open(os.path.join(ROOT, "static", "sample.png"), "rb").read()


def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c: bad.append(n)


def wait(pg, js, timeout=20000):
    import time
    end = time.time() + timeout / 1000
    while time.time() < end:
        if pg.evaluate(f"() => !!({js})"):
            return True
        pg.wait_for_timeout(200)
    return False


def search(pg, q, nav=True):
    if nav:
        pg.goto(URL + "/#showcase"); pg.wait_for_selector("#shSearch")
    pg.fill("#shSearch", q); pg.press("#shSearch", "Enter"); pg.wait_for_timeout(800)


def run(name, launch, title):
    b = launch()
    owner = b.new_context(); r = owner.request
    r.post(URL + "/api/me/signup", data={"display_name": "Ada", "dob": "1985-05-05"})
    g = r.post(URL + "/api/generate", multipart={"file": {"name": "a.png", "mimeType": "image/png", "buffer": PNG}, "mode": "relief", "photo_ack": "true"}).json()
    it = r.post(URL + "/api/showcase", data={"build_id": g["id"], "title": title, "description": "classical nude", "tags": [],
                                             "accept_guidelines": True, "nsfw": True, "visibility": "public"}).json()
    ok(f"{name}: tagged project is stored as NSFW", it.get("nsfw") is True, it)
    ctx = b.new_context(viewport={"width": 1200, "height": 900}); pg = ctx.new_page()
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL + "/"); pg.request.post(URL + "/api/me/signup", data={"display_name": "Viewer", "dob": "1990-01-01"})
    search(pg, title.split()[0])
    ok(f"{name}: hidden by default (no opt-in yet)", pg.locator("#shGrid .pcard .mature-label").count() == 0)
    s0 = pg.request.put(URL + "/api/me/mature", data={"hide_mature": False})
    ok(f"{name}: opting in saves", s0.ok, s0.text())
    search(pg, title.split()[0])
    ok(f"{name}: after opting in, shown in search as a card with a Mature content label (not hidden)", wait(pg, "document.querySelector('#shGrid .pcard .mature-label')"))
    flt = pg.evaluate("(() => { const e = document.querySelector('#shGrid .ph.nsfw img'); return e ? getComputedStyle(e).filter : '' })()")
    ok(f"{name}: card picture is blurred", "blur" in flt, flt)
    card = pg.locator("#shGrid .pcard:has(.mature-label)").first
    card.locator("a[data-open]").click()
    ok(f"{name}: opening asks Are you sure first", wait(pg, "document.querySelector('#dlgMature').open") and not pg.evaluate("document.querySelector('#dlgItem').open"))
    ok(f"{name}: focus starts on Go back", pg.evaluate("document.activeElement.id") == "matNo", pg.evaluate("document.activeElement.id"))
    pg.keyboard.press("Escape"); pg.wait_for_timeout(300)
    ok(f"{name}: Esc goes back without opening", not pg.evaluate("document.querySelector('#dlgMature').open") and not pg.evaluate("document.querySelector('#dlgItem').open"))
    card.locator("a[data-open]").click(); wait(pg, "document.querySelector('#dlgMature').open"); pg.click("#matYes")
    ok(f"{name}: Show it opens the project", wait(pg, "document.querySelector('#dlgItem').open"))
    img_f = pg.evaluate("(() => { const e = document.querySelector('#itBody img'); return e ? getComputedStyle(e).filter : 'none' })()")
    ok(f"{name}: project page picture is not blurred", "blur" not in img_f, img_f)
    pg.click("#dlgItem [data-close]"); pg.wait_for_timeout(200)
    card.locator("a[data-open]").click()
    ok(f"{name}: asked only once per visit", wait(pg, "document.querySelector('#dlgItem').open") and not pg.evaluate("document.querySelector('#dlgMature').open"))
    pg.click("#dlgItem [data-close]")
    s = pg.request.put(URL + "/api/me/mature", data={"hide_mature": True})
    ok(f"{name}: Hide mature content setting saves", s.ok, s.text())
    pg.fill("#shSearch", ""); search(pg, title.split()[0], nav=False)
    ok(f"{name}: hidden from the feed when the setting is on", pg.locator("#shGrid .pcard .mature-label").count() == 0)
    ok(f"{name}: hide setting checkbox is in the data dialog", pg.locator("#dlgData #hideMature").count() == 1)
    ok(f"{name}: publish dialog asks the NSFW question", pg.locator("#dlgPublish [name=pub_nsfw]").count() == 2)
    ok(f"{name}: no page errors", not errs, errs)
    b.close()
    if not bad: print(f"PASS {name}")


with sync_playwright() as p:
    run("chrome", lambda: p.chromium.launch(), "Venus figure study")
    try:
        run("webkit", lambda: p.webkit.launch(), "Aphrodite figure study")
    except Exception as e:
        if "Executable doesn't exist" in str(e): print("SKIP webkit", e)
        else: raise
sys.exit(1 if bad else 0)
