"""Headless Chrome: the Print button is hidden for a teen. (The teacher per-class Send switch was removed with school features, 2026-10-12.) python tests/ui_send.py http://127.0.0.1:8799  (TEMP-data server; PHOTO3D_MODE=shared recommended)"""
import os, sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8799"
R = []
def ok(n, c, x=""): R.append(bool(c)); print(("PASS " if c else "FAIL ") + n, x)
os.makedirs("previews", exist_ok=True)
J = "{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(%s)}"
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
    # a teen: Print button hidden, Download buttons stay
    t = b.new_page(viewport={"width": 1100, "height": 900}); t.goto(URL.rstrip("/") + "/#studio")
    t.evaluate("fetch('/api/me/signup'," + J % "{display_name:'Tess Teen',dob:'2011-01-01'}" + ")")
    t.reload(); t.wait_for_timeout(600)
    ok("teen: Print button hidden by CSS", t.evaluate("getComputedStyle(document.querySelector('#btnPrint')).display") == "none")
    ok("teen: data-links=0", t.evaluate("document.body.dataset.links") == "0")
    b.close()
sys.exit(0 if all(R) else 1)
