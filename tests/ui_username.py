"""Username in the account dialog: choose at sign-up (adults), generated nickname for under-18, change once, then locked with a date; a taken name is refused inline.
Chrome + WebKit, 390px.   python tests/ui_username.py URL   (use a TEMP-data server, not 8765)"""
import re, sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1]
bad = []
def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, x)
    if not c: bad.append(n)

def run(name, launch):
    try: b = launch()
    except Exception as e: print(f"SKIP {name}: {str(e).splitlines()[0][:80]}"); return
    errs = []
    def page():
        ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e))); pg.goto(URL.rstrip("/") + "/#studio"); pg.wait_for_timeout(700); return ctx, pg
    tag = name[:2]
    ctx, pg = page()
    pg.evaluate("location.hash='account'"); pg.click("#btnAccount"); pg.fill("#su_name", "Ada"); pg.fill("#su_user", f"Ada_{tag}"); pg.fill("#su_dob", "1985-05-05"); pg.click("#su_go")
    pg.wait_for_selector("#un_now", timeout=8000)
    ok(f"{name}: adult sees their chosen username in the account dialog", pg.inner_text("#un_now") == f"@Ada_{tag}")
    ok(f"{name}: the page says email is never shown", "email is never shown" in pg.inner_text("#accBody"))
    pg.click("#un_suggest"); pg.wait_for_selector("#un_sugg [data-un]"); first = pg.inner_text("#un_sugg [data-un]"); pg.click("#un_sugg [data-un]")
    ok(f"{name}: a suggestion fills the box", pg.input_value("#un_new") == first and re.match(r"^[A-Z][a-z]+[A-Z][a-z]+\d{3}$", first))
    pg.fill("#un_new", "me@example.com"); pg.click("#un_save"); pg.wait_for_selector("#accBody .inline-msg", timeout=6000)
    ok(f"{name}: a bad name is refused inline and the typed text stays", "email" in pg.inner_text("#accBody .inline-msg").lower() and pg.input_value("#un_new") == "me@example.com")
    pg.fill("#un_new", f"Maker_{tag}"); pg.click("#un_save"); pg.wait_for_selector("#un_now:has-text('Maker_')", timeout=6000)
    ok(f"{name}: change works", pg.inner_text("#un_now") == f"@Maker_{tag}")
    ok(f"{name}: then the box and button are locked and the date is shown", pg.is_disabled("#un_new") and pg.is_disabled("#un_save") and "again on" in pg.inner_text("#un_help"), pg.inner_text("#un_help"))
    ok(f"{name}: no horizontal scroll", pg.evaluate("document.documentElement.scrollWidth") <= 390)
    ctx2, pg2 = page()
    pg2.evaluate("location.hash='account'"); pg2.click("#btnAccount"); pg2.fill("#su_name", "Tess"); pg2.fill("#su_user", "MiaJohnson"); pg2.fill("#su_dob", "2011-01-01"); pg2.click("#su_go")
    pg2.wait_for_selector("#un_now", timeout=8000)
    ok(f"{name}: under-18 gets a generated nickname, not the typed name", re.match(r"^@[A-Z][a-z]+[A-Z][a-z]+\d{3}$", pg2.inner_text("#un_now")), pg2.inner_text("#un_now"))
    pg2.fill("#un_new", f"Maker_{tag}"); pg2.click("#un_save"); pg2.wait_for_selector("#accBody .inline-msg", timeout=6000)
    ok(f"{name}: a name that is taken is refused inline", "taken" in pg2.inner_text("#accBody .inline-msg"))
    ok(f"{name}: no page errors", not errs, errs)
    ctx.close(); ctx2.close(); b.close()

with sync_playwright() as p:
    run("chrome", lambda: p.chromium.launch(channel="chrome"))
    run("webkit", lambda: p.webkit.launch())
sys.exit(1 if bad else 0)
