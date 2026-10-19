"""#shTabs (Kobi g320_showcase.png): the Showcase list tabs fit/wrap from 320 to 1280 px: every tab is inside the viewport,
reachable with Tab and clickable, no horizontal page scroll, targets >= 44 px on phones (>= 24 px everywhere).
python tests/ui_shtabs.py URL   (TEMP-data server)"""
import os, sys
from playwright.sync_api import sync_playwright

URL = sys.argv[1].rstrip("/")
bad = []


def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c:
        bad.append(n)


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("CHROME") or None)
    errs = []
    for w in (320, 360, 390, 768, 1024, 1280):
        touch = w <= 768
        pg = b.new_context(viewport={"width": w, "height": 800}, has_touch=touch, is_mobile=touch).new_page()
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(URL + "/#showcase"); pg.wait_for_selector("#shTabs [data-tab=following]", state="attached"); pg.wait_for_timeout(500)
        g = pg.evaluate("""() => { const r = e => { const b = e.getBoundingClientRect(); return [b.left, b.right, b.top, b.bottom, b.width, b.height]; };
          return { vw: innerWidth, sw: document.documentElement.scrollWidth, row: r(document.querySelector('#shTabs')),
                   tabs: [...document.querySelectorAll('#shTabs button')].map(e => ({ k: e.dataset.tab, b: r(e), cut: e.scrollWidth > e.clientWidth + 1 })) }; }""")
        L, R = g["row"][0], g["row"][1]
        ok(f"chrome {w}px: no horizontal page scroll", g["sw"] <= g["vw"], g)
        ok(f"chrome {w}px: the tab row fits the viewport", L >= 0 and R <= g["vw"] + 0.5, g["row"])
        ok(f"chrome {w}px: all 4 tabs are fully inside the row and the viewport, none clipped",
           len(g["tabs"]) == 4 and all(t["b"][0] >= L - 0.5 and t["b"][1] <= R + 0.5 and t["b"][1] <= g["vw"] and not t["cut"] for t in g["tabs"]), g["tabs"])
        mh = 44 if touch else 24
        ok(f"chrome {w}px: every tab is at least {mh}x{mh} px", all(t["b"][4] >= mh and t["b"][5] >= mh for t in g["tabs"]), [t["b"][4:] for t in g["tabs"]])
        pg.focus("#shTabs [data-tab=trending]")
        seen = []
        for _ in range(3):
            pg.keyboard.press("Tab"); seen.append(pg.evaluate("document.activeElement.dataset.tab || ''"))
        ok(f"chrome {w}px: Tab reaches Newest, For You and Following in order", seen == ["free", "foryou", "following"], seen)
        pg.keyboard.press("Enter"); pg.wait_for_timeout(300)
        ok(f"chrome {w}px: Following is selectable from the keyboard", pg.get_attribute("#shTabs [data-tab=following]", "aria-pressed") == "true")
        if w == 320:
            pg.locator("#shTabs").screenshot(path=os.path.join(os.environ.get("SHOTS", "/tmp"), "shtabs-320.png"))
        pg.context.close()
    ok("chrome: no page errors", not errs, errs[:3])
    b.close()
print("ALL PASS" if not bad else f"{len(bad)} FAIL"); sys.exit(1 if bad else 0)
