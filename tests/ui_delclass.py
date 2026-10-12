"""Delete class uses an in-app dialog, never confirm(): Keep (focused first) and Esc keep the class; Delete removes only that class.  390px, Chrome + WebKit."""
import sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1]; bad = []
def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c: bad.append(n)
def run(name, launch):
    try: b = launch()
    except Exception as e: print(f"SKIP {name}: {str(e).splitlines()[0][:80]}"); return
    errs, native = [], []
    ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True); r = ctx.request
    r.post(URL + "/api/me/signup", data={"display_name": "Ms T", "dob": "1980-01-01"})
    a = r.post(URL + "/api/classrooms", data={"name": f"Alpha {name}", "password": "bluebird-77"}).json()["code"]
    z = r.post(URL + "/api/classrooms", data={"name": f"Zulu {name}", "password": "bluebird-77"}).json()["code"]
    pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: (native.append(d.type), d.dismiss()))
    pg.goto(URL); pg.wait_for_timeout(700); pg.click("#mainNav [data-view=learn]"); pg.click("#btnTeacher"); pg.wait_for_selector(f'[data-dr="{a}"]')
    pg.click(f'[data-dr="{a}"]'); pg.wait_for_selector("#dlgDelClass[open]")
    ok(f"{name}: in-app dialog names the class and focuses Keep", f"Alpha {name}" in pg.inner_text("#dlgDelClass") and pg.evaluate("document.activeElement.id") == "dcKeep" and "can't be undone" in pg.inner_text("#dlgDelClass"))
    ok(f"{name}: buttons are at least 44px", all(pg.locator(s).bounding_box()["height"] >= 43.5 for s in ("#dcKeep", "#dcGo")))
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
    codes = [x["code"] for x in r.get(URL + "/api/classrooms").json()["rooms"]]
    ok(f"{name}: Esc keeps the class", not pg.is_visible("#dlgDelClass") and a in codes)
    pg.click(f'[data-dr="{a}"]'); pg.wait_for_selector("#dlgDelClass[open]"); pg.click("#dcKeep"); pg.wait_for_timeout(200)
    ok(f"{name}: Keep keeps the class", a in [x["code"] for x in r.get(URL + "/api/classrooms").json()["rooms"]])
    pg.click(f'[data-dr="{a}"]'); pg.wait_for_selector("#dlgDelClass[open]"); pg.click("#dcGo"); pg.wait_for_timeout(800)
    codes = [x["code"] for x in r.get(URL + "/api/classrooms").json()["rooms"]]
    ok(f"{name}: Delete removes only that class", a not in codes and z in codes and not pg.is_visible("#dlgDelClass"), codes)
    ok(f"{name}: no native confirm/alert box was used", not native, native)
    ok(f"{name}: no page errors", not errs, errs)
    ctx.close(); b.close()
with sync_playwright() as p:
    run("chrome", lambda: p.chromium.launch(channel="chrome"))
    run("webkit", lambda: p.webkit.launch())
sys.exit(1 if bad else 0)
