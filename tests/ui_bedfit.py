"""Pilot polish: a model that is too big for the chosen printer shows a friendly "won't fit your bed" message BEFORE slicing
(Will-it-print box in Edit) and, if you press Slice anyway, the server's friendly too-big guidance (Scale / Split / shrink-to-fit) -
never "Unprocessable Content" or "Slicer failed".  Chrome + WebKit, 390 px.   python tests/ui_bedfit.py URL  (TEMP-data server)"""
import os, shutil, sys, tempfile
import trimesh
from playwright.sync_api import sync_playwright
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__))); import zws_open; zws_open.install()   # C: phone panels start as chips
URL = sys.argv[1].rstrip("/"); bad = []


def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c: bad.append(n)


def run(name, launch, stl):
    try: b = launch()
    except Exception as e: print(f"SKIP {name}: {str(e).splitlines()[0][:80]}"); return
    pg = b.new_page(viewport={"width": 390, "height": 844})
    pg.goto(URL + "/#edit"); pg.wait_for_timeout(1000)
    pg.set_input_files("#editFile", stl)
    pg.wait_for_selector("#editResult:not([hidden])", timeout=60000)
    pg.wait_for_selector("#editWill .willbox", timeout=60000)
    will = pg.inner_text("#editWill")
    ok(f"{name}: before slicing, the Will-it-print box says it won't fit your bed", "Won't fit your bed" in will and "Won't print as is" in will, will)
    ok(f"{name}: ... with the sizes and what to do (scale %, shrink-to-fit, Split)", "250 × 188 × 3 mm" in will and "88%" in will and "Split" in will, will)
    pg.click("#spGo")
    pg.wait_for_selector("#spOut [role=alert]", timeout=30000)
    out = pg.inner_text("#spOut")
    ok(f"{name}: pressing Slice anyway shows the friendly too-big guidance", "can only print up to" in out and "Split" in out and "Scale" in out, out)
    ok(f"{name}: never a raw HTTP status or 'Slicer failed'", "Unprocessable" not in out and "Slicer failed" not in out, out)
    b.close()
    if not bad: print(f"PASS {name}")


d = tempfile.mkdtemp(prefix="zeim-bedfit-")
try:
    stl = os.path.join(d, "too-big-plate.stl"); trimesh.creation.box([250, 188, 3]).export(stl)
    with sync_playwright() as p:
        run("chrome", lambda: p.chromium.launch(), stl)
        run("webkit", lambda: p.webkit.launch(), stl)
finally:
    shutil.rmtree(d, ignore_errors=True)
sys.exit(1 if bad else 0)
