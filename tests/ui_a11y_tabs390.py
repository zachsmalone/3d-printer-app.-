"""A11y sweep at phone width (390 px): the Mode select has an accessible name ('Mode') even though its label is visually hidden,
and every main tab (Studio, Showcase, Slicer, CAD, Lithophane, Smart Fix, Account) has ZERO critical/serious axe-core issues,
in light and dark theme and in Experienced mode.  Chrome + WebKit.   python tests/ui_a11y_tabs390.py URL  (TEMP-data server)"""
import json, os, sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1].rstrip("/"); bad = []
AXE = os.environ.get("AXE_JS") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "axe.min.js")
VIEWS = ("studio", "showcase", "slicer", "cad", "lithophane", "smartfix", "account")
AXE_RUN = ("axe.run(document).then(r => r.violations.filter(v => ['critical','serious'].includes(v.impact))"
           ".map(v => ({id: v.id, impact: v.impact, n: v.nodes.length, t: v.nodes.slice(0, 3).map(n => n.target.join(' '))})))")


def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c: bad.append(n)


def sweep(pg, name, tag):
    for v in VIEWS:
        pg.goto(URL + "/#" + v); pg.wait_for_timeout(900)
        pg.add_script_tag(path=AXE)
        res = pg.evaluate(AXE_RUN)
        ok(f"{name}: {tag}: #{v} has no critical/serious axe issues", not res, json.dumps(res))


def run(name, launch):
    try: b = launch()
    except Exception as e: print(f"SKIP {name}: {str(e).splitlines()[0][:80]}"); return
    ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, bypass_csp=True)
    pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL + "/#studio"); pg.wait_for_timeout(1200)
    ok(f"{name}: 390px: the Mode select is a combobox named 'Mode'", pg.get_by_role("combobox", name="Mode").count() == 1)
    ok(f"{name}: 390px: its label is visually hidden but still the select's label",
       pg.evaluate("(() => { const e = document.getElementById('modeSel'); const l = e.labels[0]; return e.labels.length === 1 && l.textContent.trim() === 'Mode' && l.getBoundingClientRect().width <= 1; })()"))
    sweep(pg, name, "390 light")
    pg.goto(URL + "/#studio"); pg.wait_for_timeout(600)
    pg.select_option("#modeSel", "expert"); pg.wait_for_timeout(300)
    sweep(pg, name, "390 light Experienced")
    pg.goto(URL + "/#studio"); pg.wait_for_timeout(600)
    pg.select_option("#modeSel", "beginner"); pg.click("#themeToggle"); pg.wait_for_timeout(200)
    sweep(pg, name, "390 dark")
    ok(f"{name}: no page errors", not errs, errs[:3])
    ctx.close(); b.close()
    if not bad: print(f"PASS {name}")


with sync_playwright() as p:
    run("chrome", lambda: p.chromium.launch())
    run("webkit", lambda: p.webkit.launch())
sys.exit(1 if bad else 0)
