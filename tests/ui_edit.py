"""Headless UI test of the Edit workspace + screenshots. python tests/ui_edit.py [url]  (server must be running)"""
import sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765"
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
    pg = b.new_page(viewport={"width": 1440, "height": 1000})
    pg.on("pageerror", lambda e: errs.append("PAGEERR " + str(e))); pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.goto(URL); pg.wait_for_timeout(600)
    pg.evaluate("localStorage.level='beginner'"); pg.reload(); pg.wait_for_timeout(500)
    # clean history
    for x in pg.evaluate("fetch('/api/builds').then(r=>r.json()).then(j=>j.builds.map(b=>b.id))"):
        pg.evaluate(f"fetch('/api/builds/{x}',{{method:'DELETE'}})")
    pg.click('#mainNav [data-view=edit]'); pg.wait_for_timeout(500)
    pg.screenshot(path="previews/ui_edit_start.png")
    pg.click("#editSample"); pg.wait_for_selector("#editResult:not([hidden])", timeout=60000); pg.wait_for_timeout(1500)
    pg.screenshot(path="previews/ui_edit_beginner.png")
    pg.click('[data-big=fix]'); pg.wait_for_timeout(2500)
    pg.click('[data-big=hollow]'); pg.wait_for_timeout(300); pg.click('#bHollowGo'); pg.wait_for_function("document.querySelectorAll('#editOps li').length>=4", timeout=60000); pg.wait_for_timeout(1500)
    pg.select_option("#modeSel", "expert"); pg.wait_for_timeout(600)
    pg.click('#editPanel details.tool:nth-of-type(2) summary')            # cut
    pg.fill('form[data-form=cut] [name=position]', '20'); pg.wait_for_timeout(300)
    pg.screenshot(path="previews/ui_edit.png")
    pg.click('#editPanel details.tool:nth-of-type(6) summary')            # text
    pg.fill('form[data-form=text] [name=text]', 'ZEIM'); pg.click('form[data-form=text] button'); pg.wait_for_function("document.querySelectorAll('#editOps li').length>=5", timeout=60000); pg.wait_for_timeout(1200)
    pg.screenshot(path="previews/ui_edit_expert_text.png")
    pg.click('#eUndo'); pg.wait_for_timeout(1200)
    print("ops:", pg.evaluate("[...document.querySelectorAll('#editOps li')].map(l=>l.textContent+(l.className?' ['+l.className+']':''))"))
    print("stats:", pg.inner_text('#editStats'))
    b.close()
print("JS errors:", errs or "none")
