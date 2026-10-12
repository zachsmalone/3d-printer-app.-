"""Headless check: no horizontal scroll at phone/tablet widths on Studio, Showcase, Edit, Learn; every nav item reachable.
Needs Chrome + playwright (optional, not part of pytest). python tests/ui_mobile.py [url]"""
import sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765"
bad = []
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
    for w in (320, 375, 390, 768):
        pg = b.new_page(viewport={"width": w, "height": 800}); pg.goto(URL.rstrip("/") + "/#studio"); pg.wait_for_timeout(600)
        for view in ("showcase", "slicer", "cad", "lithophane", "smartfix", "account"):
            pg.click(f"#mainNav [data-view={view}]"); pg.wait_for_timeout(300)
            sw = pg.evaluate("document.documentElement.scrollWidth")
            if sw > w: bad.append((w, view, "scrollWidth", sw))
            for sel in [f"#mainNav [data-view={v}]" for v in ("showcase", "slicer", "cad", "lithophane", "smartfix", "account")] + ["#modeSel", "#themeToggle"]:
                bx = pg.locator(sel).bounding_box()
                if not bx or bx["x"] < -1 or bx["x"] + bx["width"] > w + 1 or bx["height"] < 43: bad.append((w, view, sel, bx))
        pg.screenshot(path=f"previews/ui_mobile_{w}.png"); pg.close()
    b.close()
print("OK" if not bad else bad); sys.exit(1 if bad else 0)
