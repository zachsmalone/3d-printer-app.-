"""Dark mode toggle (sun/moon, upper right of the top bar): aria, 44px target, persistence, prefers-color-scheme on first visit only, every page.
Run against a live server: BASE=http://127.0.0.1:8765 python tests/ui_theme_toggle.py"""
import os, sys
from playwright.sync_api import sync_playwright
BASE = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("BASE", "http://127.0.0.1:8765")).rstrip("/")
fails = []
def ok(msg, cond):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)
theme = "document.documentElement.getAttribute('data-theme') || 'light'"
with sync_playwright() as p:
    b = p.chromium.launch()
    for vw in ((390, 844), (1280, 800)):
        tag = f"{vw[0]}px"
        c = b.new_context(viewport={"width": vw[0], "height": vw[1]}, color_scheme="light"); pg = c.new_page()
        pg.goto(BASE + "/"); pg.wait_for_selector("#themeToggle svg")
        t = pg.locator("#themeToggle")
        ok(f"{tag}: default light", pg.evaluate(theme) == "light")
        ok(f"{tag}: aria-pressed false + label", t.get_attribute("aria-pressed") == "false" and t.get_attribute("aria-label") == "Dark mode")
        bb = t.bounding_box(); bar = pg.locator(".topbar").bounding_box()
        ok(f"{tag}: 44px target", bb["width"] >= 44 and bb["height"] >= 44)
        ok(f"{tag}: upper right of top bar", bb["x"] + bb["width"] > bar["x"] + bar["width"] - 60 and bb["y"] < bar["y"] + bar["height"])
        t.click()
        ok(f"{tag}: click -> dark, aria-pressed true, saved", pg.evaluate(theme) == "dark" and t.get_attribute("aria-pressed") == "true" and pg.evaluate("localStorage.theme") == "dark")
        pg.reload(); pg.wait_for_selector("#themeToggle svg")
        ok(f"{tag}: persists after reload", pg.evaluate(theme) == "dark" and pg.locator("#themeToggle").get_attribute("aria-pressed") == "true")
        pg.keyboard.press("Tab")
        pg.focus("#themeToggle"); pg.keyboard.press("Enter")
        ok(f"{tag}: keyboard toggles back to light, saved", pg.evaluate(theme) == "light" and pg.evaluate("localStorage.theme") == "light")
        for path in ("/static/privacy.html", "/static/terms.html", "/static/COMMUNITY_GUIDELINES.html"):
            pg.goto(BASE + path); pg.wait_for_selector("#themeToggle svg")
            ok(f"{tag}: toggle present on {path}", pg.locator("#themeToggle").is_visible())
        c.close()
    c = b.new_context(color_scheme="dark"); pg = c.new_page(); pg.goto(BASE + "/"); pg.wait_for_selector("#themeToggle svg")
    ok("no saved choice + OS dark -> dark", pg.evaluate(theme) == "dark")
    pg.click("#themeToggle"); pg.reload(); pg.wait_for_selector("#themeToggle svg")
    ok("saved light beats OS dark", pg.evaluate(theme) == "light"); c.close()
    c = b.new_context(color_scheme="light"); c.add_init_script("localStorage.theme='dark'"); pg = c.new_page()
    pg.goto(BASE + "/", wait_until="commit"); pg.wait_for_selector("html[data-theme=dark]", timeout=3000)
    ok("no flash: dark set before DOMContentLoaded", pg.evaluate("document.documentElement.dataset.theme") == "dark"); c.close()
    b.close()
print(f"{len(fails)} failed"); sys.exit(1 if fails else 0)
