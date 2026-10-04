"""Headless Chrome: teacher's per-class Send switch (off by default, confirm dialog, Cancel keeps it off) and the Print button
hidden for a teen. python tests/ui_send.py http://127.0.0.1:8799  (TEMP-data server; PHOTO3D_MODE=shared recommended)"""
import os, sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8799"
R = []
def ok(n, c, x=""): R.append(bool(c)); print(("PASS " if c else "FAIL ") + n, x)
os.makedirs("previews", exist_ok=True)
J = "{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(%s)}"
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
    pg = b.new_page(viewport={"width": 1100, "height": 900}); pg.goto(URL)
    pg.evaluate("fetch('/api/me/signup'," + J % "{display_name:'Ada Adult',dob:'1985-05-05'}" + ")")
    pg.evaluate("fetch('/api/classrooms'," + J % "{name:'Room 12',password:'long-pass-1'}" + ")")
    pg.reload(); pg.wait_for_timeout(500)
    pg.click("#mainNav [data-view=learn]"); pg.click("#btnTeacher"); pg.wait_for_selector("input[data-send]")
    sw = pg.locator("input[data-send]").first
    ok("switch is OFF by default", not sw.is_checked())
    sw.click(force=True); pg.wait_for_selector("#dlgSend[open]")
    txt = pg.inner_text("#dlgSend")
    ok("dialog names the class and the under-13 line", "Room 12" in txt and "Students under 13 still can't use outside apps." in txt)
    ok("Cancel has focus", pg.evaluate("document.activeElement.id") == "sendCancel")
    pg.screenshot(path="previews/ui_send_dialog.png")
    pg.click("#sendCancel"); pg.wait_for_timeout(300)
    ok("Cancel keeps it OFF", not pg.locator("input[data-send]").first.is_checked())
    pg.locator("input[data-send]").first.click(force=True); pg.wait_for_selector("#dlgSend[open]"); pg.click("#sendOn"); pg.wait_for_timeout(800)
    ok("Turn on -> switch ON with 'On since'", pg.locator("input[data-send]").first.is_checked() and "On since" in pg.inner_text("#teacherBody"))
    pg.screenshot(path="previews/ui_send_switch_on.png")
    # a teen: Print button hidden, Download buttons stay
    t = b.new_page(viewport={"width": 1100, "height": 900}); t.goto(URL)
    t.evaluate("fetch('/api/me/signup'," + J % "{display_name:'Tess Teen',dob:'2011-01-01'}" + ")")
    t.reload(); t.wait_for_timeout(600)
    ok("teen: Print button hidden by CSS", t.evaluate("getComputedStyle(document.querySelector('#btnPrint')).display") == "none")
    ok("teen: data-links=0", t.evaluate("document.body.dataset.links") == "0")
    b.close()
sys.exit(0 if all(R) else 1)
