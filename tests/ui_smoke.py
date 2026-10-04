"""Headless UI smoke test + screenshots (needs system Chrome). python tests/ui_smoke.py"""
import sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765"
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.goto(URL); pg.wait_for_timeout(800)
    pg.screenshot(path="previews/ui_studio_empty.png")
    pg.click("#btnSample"); pg.click("#btnBuild"); pg.wait_for_selector("#result:not([hidden])", timeout=60000); pg.wait_for_timeout(1500)
    pg.screenshot(path="previews/ui_studio_built.png")
    pg.click('#modeCards [data-mode=popart]'); pg.click("#btnBuild"); pg.wait_for_timeout(2500)
    pg.click("#btnPrint"); pg.wait_for_timeout(600); pg.screenshot(path="previews/ui_print_dialog.png"); pg.click("#dlgPrint [data-close]")
    pg.click('#mainNav [data-view=showcase]'); pg.wait_for_timeout(800); pg.screenshot(path="previews/ui_showcase.png")
    pg.click('#mainNav [data-view=learn]'); pg.wait_for_timeout(800); pg.click('[data-lesson=lithophanes]'); pg.wait_for_timeout(600)
    pg.screenshot(path="previews/ui_learn.png")
    pg.click("#btnSettings"); pg.wait_for_timeout(600); pg.click('[data-tab=tAcc]'); pg.wait_for_timeout(400); pg.screenshot(path="previews/ui_settings_accounts.png")
    b.close()
print("JS errors:", errs or "none")
