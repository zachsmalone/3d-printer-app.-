"""Sun/moon toggle: switches light/dark on the home page and the CAD workspace, and is remembered after reload. python tests/ui_theme_toggle.py URL"""
import sys
from playwright.sync_api import sync_playwright
U = sys.argv[1].rstrip("/"); bad = []
with sync_playwright() as p:
    b = p.chromium.launch()
    for path in ("/#studio", "/static/cad.html"):
        pg = b.new_page(color_scheme="light"); pg.goto(U + path); pg.wait_for_timeout(1500)
        th = lambda: pg.evaluate("document.documentElement.getAttribute('data-theme') || 'light'")
        if pg.locator("#themeToggle").count() != 1: bad.append(path + " no toggle"); continue
        pg.click("#themeToggle"); pg.wait_for_timeout(200)
        if th() != "dark": bad.append(path + " click did not switch to dark")
        pg.reload(); pg.wait_for_timeout(800)
        if th() != "dark": bad.append(path + " dark not remembered")
        pg.click("#themeToggle"); pg.wait_for_timeout(200)
        if th() != "light" or pg.evaluate("localStorage.theme") != "light": bad.append(path + " did not switch back")
        pg.close()
    # Windows contrast theme on: the toggle explains why it has no visible effect (once), never blocks
    pg = b.new_page(forced_colors="active"); pg.goto(U + "/#studio"); pg.wait_for_timeout(1200)
    if "contrast theme" not in (pg.get_attribute("#themeToggle", "title") or ""): bad.append("forced-colors: tooltip missing")
    pg.click("#themeToggle"); pg.wait_for_timeout(200)
    if "Contrast themes" not in (pg.text_content("#forcedNote") or ""): bad.append("forced-colors: note missing")
    pg.click("#forcedNote button"); pg.click("#themeToggle"); pg.wait_for_timeout(200)
    if pg.locator("#forcedNote").count(): bad.append("forced-colors: note shown twice")
    if pg.evaluate("document.documentElement.scrollWidth > innerWidth + 1"): bad.append("forced-colors: horizontal scroll")
    pg.close()
    b.close()
print("FAIL", bad) if bad else print("all ok")
sys.exit(1 if bad else 0)
