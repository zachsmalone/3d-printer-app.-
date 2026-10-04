"""iOS file-picker regression: the Edit tab's 'Choose a 3D file' input must NOT carry an `accept` list of bare extensions
(iOS Safari greys .stl/.obj/.3mf out), and the file type is checked by name in JS instead. Runs in Chrome AND WebKit (Safari's engine)
if installed.  python tests/ui_files.py URL    NOT a real iPhone: WebKit-on-Linux does not show the iOS picker."""
import os, sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STL = open(os.path.join(ROOT, "static", "sample_model.stl"), "rb").read()
R = []
def ok(n, c, x=""): R.append(bool(c)); print(("PASS " if c else "FAIL ") + n, x)

def run(name, launch):
    try:
        b = launch()
    except Exception as e:
        print(f"SKIP {name}: cannot launch ({str(e).splitlines()[0][:80]})"); return
    errs = []
    def fresh():
        ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=name != "webkit-desktop")
        pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(URL); pg.wait_for_timeout(500); pg.click("#mainNav [data-view=edit]"); pg.wait_for_timeout(300)
        return ctx, pg
    ctx, pg = fresh()
    ok(f"{name}: #editFile has no accept attribute", pg.get_attribute("#editFile", "accept") is None)
    for fname, mime, label in (("cube.stl", "", "empty MIME"), ("CUBE.STL", "application/octet-stream", "upper-case + octet-stream"), ("part.3mf", "model/3mf", "model/3mf")):
        if label != "empty MIME": ctx.close(); ctx, pg = fresh()
        pg.set_input_files("#editFile", {"name": fname, "mimeType": mime, "buffer": STL})
        pg.wait_for_timeout(1200)
        # a 3MF with STL bytes is rejected by the SERVER (fine); what matters here is that the PAGE did not refuse by name
        ok(f"{name}: {fname} ({label}) is not refused by the page", not pg.is_visible("#editModelMsg"))
        if fname.lower().endswith(".stl"):
            pg.wait_for_selector("#editPanel:not([hidden])", timeout=20000); ok(f"{name}: {fname} ({label}) really opens in the editor", True)
    ctx.close(); ctx, pg = fresh()
    pg.set_input_files("#editFile", {"name": "notes.txt", "mimeType": "text/plain", "buffer": b"hello"})
    pg.wait_for_timeout(500)
    ok(f"{name}: notes.txt gets a friendly inline message", pg.is_visible("#editModelMsg") and "3D model" in pg.inner_text("#editModelMsg"), pg.inner_text("#editModelMsg"))
    ok(f"{name}: ...and nothing was opened", not pg.is_visible("#editPanel"))
    pg.set_input_files("#editFile", {"name": "ok.stl", "mimeType": "", "buffer": STL}); pg.wait_for_timeout(1200)
    ok(f"{name}: the message clears on the next good file", not pg.is_visible("#editModelMsg"))
    ok(f"{name}: no page errors", not errs, errs)
    ctx.close(); b.close()

with sync_playwright() as p:
    run("chrome", lambda: p.chromium.launch(channel="chrome"))
    run("webkit", lambda: p.webkit.launch())
sys.exit(0 if all(R) and R else 1)
