"""Slicer (Edit) import regression: picked or dropped STL/3MF/OBJ files must load, or say why. python tests/ui_slicer_import.py URL"""
import os, sys, tempfile
import trimesh
from playwright.sync_api import sync_playwright
URL = sys.argv[1].rstrip("/")
d = tempfile.mkdtemp(prefix="zeim-imp-")
box = trimesh.creation.box((20, 20, 20))
paths = {}
for n in ("a.stl", "b.3mf", "c.obj"):
    paths[n] = os.path.join(d, n); box.export(paths[n])
def wait(pg, js, timeout=60000):     # the page's CSP forbids eval, so poll from Python instead of wait_for_function
    import time; t = time.time()
    while time.time() - t < timeout / 1000:
        if pg.evaluate("() => " + js): return
        pg.wait_for_timeout(200)
    raise TimeoutError(js)
errs, fails = [], []
def check(cond, what):
    (print("ok  ", what) if cond else fails.append(what))
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome") if os.environ.get("ZEIM_UI_CHANNEL") else p.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL + "/#slicer"); pg.wait_for_selector("#editChooseModel", state="visible", timeout=20000)
    shown = "!document.querySelector('#editResult').hidden"
    for n in paths:   # one file through the picker
        with pg.expect_file_chooser() as fc: pg.click("#editChooseModel")
        fc.value.set_files(paths[n])
        try: wait(pg, shown, timeout=60000); ok = True
        except Exception as ex: ok = False; print(ex)
        check(ok, f"picked {n} loads"); pg.click("#editClose"); pg.wait_for_timeout(200)
    with pg.expect_file_chooser() as fc: pg.click("#editChooseModel")      # two files -> parts-of-one-print dialog
    fc.value.set_files([paths["a.stl"], paths["b.3mf"]])
    wait(pg, "document.querySelector('#dlgMulti').open", timeout=10000)
    pg.click("#multiPlate")
    try: wait(pg, shown + " && !document.querySelector('#dlgMulti').open", timeout=60000); ok = True
    except Exception: ok = False
    check(ok, "two files as parts of one print load")
    # drop a file onto the open model's viewer (no drop box visible): must load, not be opened by the browser
    data = open(paths["c.obj"], "rb").read().decode()
    before = pg.evaluate("document.querySelector('#editStats')?.textContent || ''")
    pg.evaluate("""(t) => { const dt = new DataTransfer(); dt.items.add(new File([t], 'dropped.obj'));
        const el = document.querySelector('#editViewer') || document.querySelector('#viewEdit');
        const ev = new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }); el.dispatchEvent(ev);
        window.__dropPrevented = ev.defaultPrevented; }""", data)
    pg.wait_for_timeout(300)
    check(pg.evaluate("window.__dropPrevented"), "drop on the viewer is handled by ZEIM (not by the browser)")
    try: wait(pg, "!document.querySelector('#editBusy') || document.querySelector('#editBusy').hidden")
    except Exception: pass
    check(pg.is_visible("#editResult"), "dropped file loads")
    pg.click("#editClose"); pg.wait_for_timeout(200)
    pg.evaluate("""() => { const dt = new DataTransfer(); dt.items.add(new File([''], 'empty.stl'));
        const i = document.querySelector('#editFile'); i.files = dt.files; i.dispatchEvent(new Event('change')); }""")
    pg.wait_for_timeout(300)
    check("empty" in pg.inner_text("#editModelMsg").lower(), "an empty file says so")
    b.close()
check(not errs, f"no page errors {errs}")
print("FAIL:", fails) if fails else print("all ok")
sys.exit(1 if fails else 0)
