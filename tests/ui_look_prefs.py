"""Colours & accessibility dialog: theme light/dark/system, accent, high contrast, colour-vision palettes; saved across reload. python tests/ui_look_prefs.py URL"""
import sys
from playwright.sync_api import sync_playwright
U = sys.argv[1].rstrip("/"); bad = []
with sync_playwright() as p:
    b = p.chromium.launch(); errs = []
    for path in ("/#studio", "/static/cad.html"):
        pg = b.new_page(color_scheme="dark"); pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(U + path); pg.wait_for_timeout(1200)
        at = lambda k: pg.evaluate(f"document.documentElement.getAttribute('data-{k}')")
        if pg.locator("#lookBtn").count() != 1: bad.append(path + " no look button"); continue
        pg.click("#lookBtn"); pg.wait_for_selector("#dlgLook[open]")
        pg.select_option("#lookAccent", "teal"); pg.check("#lookContrast"); pg.select_option("#lookCb", "redgreen"); pg.select_option("#lookTheme", "light")
        if (at("accent"), at("contrast"), at("cb"), at("theme")) != ("teal", "high", "redgreen", None): bad.append(path + " not applied")
        ok = pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--ok').trim().toLowerCase()")
        if ok != "#005a9c": bad.append(path + f" red-green palette not used ({ok})")
        pg.keyboard.press("Escape"); pg.reload(); pg.wait_for_timeout(800)
        if (at("accent"), at("contrast"), at("cb")) != ("teal", "high", "redgreen"): bad.append(path + " not remembered")
        pg.click("#lookBtn"); pg.select_option("#lookTheme", "system")
        if at("theme") != "dark": bad.append(path + " system theme did not follow the device (dark)")
        pg.click("#lookReset")
        if at("accent") or at("cb") or at("contrast"): bad.append(path + " reset did not clear")
        pg.close()
    b.close()
if errs: bad.append(f"page errors {errs}")
print("FAIL", bad) if bad else print("all ok")
sys.exit(1 if bad else 0)
