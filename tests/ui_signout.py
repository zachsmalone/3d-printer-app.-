"""Sign out in Account: plain warning, adults must see + confirm their recovery code first, teens confirm they can't come back; after sign-out the
browser is empty; an adult gets back in with the code.  390px, Chrome + WebKit (axe in Chrome).  python tests/ui_signout.py URL"""
import json, os, re, sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1]
AXE = os.environ.get("AXE_JS") or "/workspace/a11y-tools/node_modules/axe-core/axe.min.js"
bad = []
def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c: bad.append(n)

def run(name, launch, with_axe):
    try: b = launch()
    except Exception as e: print(f"SKIP {name}: {str(e).splitlines()[0][:80]}"); return
    errs = []; tag = name[:2] + str(os.getpid() % 997)
    ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True, bypass_csp=True)
    pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e))); pg.goto(URL.rstrip("/") + "/#studio"); pg.wait_for_timeout(700)
    pg.evaluate("location.hash='account'"); pg.click("#btnAccount"); pg.fill("#su_name", "Ms Out"); pg.fill("#su_user", f"MsOut_{tag}"); pg.fill("#su_dob", "1980-02-02"); pg.click("#su_go"); pg.wait_for_selector("#un_now", timeout=8000)
    pg.evaluate("document.querySelector('#dlgAccount').close()"); pg.select_option("#modeSel", "expert"); pg.wait_for_timeout(300)
    pg.evaluate("location.hash='account'"); pg.click("#btnAccount"); pg.click("#so_open"); pg.wait_for_selector("#dlgSignout[open]")
    ok(f"{name}: sign-out dialog explains there are no passwords and needs the recovery code", "no passwords yet" in pg.inner_text("#soBody") and "recovery code" in pg.inner_text("#soBody"))
    ok(f"{name}: Sign out stays off until the code is shown and the box ticked", pg.is_disabled("#soGo") and pg.is_disabled("#soOk"))
    pg.click("#soCodeBtn"); pg.wait_for_selector("#soCode .code")
    code = pg.inner_text("#soCode .code").strip()
    ok(f"{name}: a recovery code is shown", len(re.sub(r"[^A-Z0-9]", "", code)) == 16, code)
    if with_axe and os.path.exists(AXE):
        pg.add_script_tag(path=AXE)
        r = pg.evaluate("axe.run(document.querySelector('#dlgSignout'), {runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','best-practice']}}).then(r=>r.violations.map(v=>v.id))")
        ok(f"axe: sign-out dialog", not r, r)
    pg.check("#soOk"); ok(f"{name}: ticking the box turns Sign out on", not pg.is_disabled("#soGo"))
    pg.click("#soGo"); pg.wait_for_load_state(); pg.wait_for_timeout(1200)
    ok(f"{name}: after sign-out the browser has no account",
       "sign up" in (pg.get_attribute("#btnAccount", "aria-label") or "") and not pg.locator("#classBar").count())
    ok(f"{name}: the page says you are signed out", "signed out" in pg.inner_text("#toasts").lower(), pg.inner_text("#toasts"))
    pg.evaluate("location.hash='account'"); pg.click("#btnAccount"); pg.click("#accBody details.recover summary"); pg.fill("#rc_code", "WRONG-CODE-0000-0000"); pg.click("#rc_go"); pg.wait_for_selector("#accBody .inline-msg")
    ok(f"{name}: a wrong code is refused inline and the typed code stays", "didn't work" in pg.inner_text("#accBody .inline-msg") and pg.input_value("#rc_code") == "WRONG-CODE-0000-0000")
    pg.fill("#rc_code", code); pg.click("#rc_go"); pg.wait_for_selector("#rc_done")
    ok(f"{name}: the right code brings the account back and shows a NEW code", f"@MsOut_{tag}" in pg.inner_text("#accBody") and code not in pg.inner_text("#accBody .code"))
    pg.click("#rc_done"); pg.wait_for_load_state(); pg.wait_for_timeout(1000)
    ok(f"{name}: signed in again after reload", "Ms Out" in pg.inner_text("#btnAccount") or "Ms Out" in (pg.get_attribute("#btnAccount", "aria-label") or ""))
    ctx.close()
    # teen
    ctx = b.new_context(viewport={"width": 390, "height": 844}, bypass_csp=True); pg = ctx.new_page(); pg.goto(URL.rstrip("/") + "/#studio"); pg.wait_for_timeout(600)
    pg.evaluate("location.hash='account'"); pg.click("#btnAccount"); pg.fill("#su_name", "Tess"); pg.fill("#su_dob", "2011-01-01"); pg.click("#su_go"); pg.wait_for_selector("#un_now", timeout=8000)
    pg.click("#so_open"); pg.wait_for_selector("#dlgSignout[open]")
    ok(f"{name}: a teen is told plainly the account can't be opened again", "can't be opened again" in pg.inner_text("#soBody") and pg.is_disabled("#soGo"))
    pg.check("#soOk"); pg.click("#soGo"); pg.wait_for_load_state(); pg.wait_for_timeout(1000)
    ok(f"{name}: teen sign-out works", "sign up" in (pg.get_attribute("#btnAccount", "aria-label") or ""))
    ok(f"{name}: no page errors", not errs, errs)
    ctx.close(); b.close()

with sync_playwright() as p:
    run("chrome", lambda: p.chromium.launch(channel="chrome"), True)
    run("webkit", lambda: p.webkit.launch(), False)
sys.exit(1 if bad else 0)
