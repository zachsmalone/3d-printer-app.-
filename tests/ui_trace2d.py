"""'Logo & Drawing to 3D' in a real browser: the card, the settings panel (labels, keyboard, 44 px targets), the live traced
outline, and one build per output (shape, cookie cutter, stamp, colour layers) shown in the 3D viewer like every build.
python tests/ui_trace2d.py URL [SHOT_DIR]"""
import os, sys, tempfile
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright
URL = sys.argv[1].rstrip("/"); SHOTS = sys.argv[2] if len(sys.argv) > 2 else None; bad = []


def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c: bad.append(n)


def logo(path, colour=False):
    im = Image.new("RGB", (600, 300), "white"); d = ImageDraw.Draw(im)
    try: f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 150)
    except OSError: f = ImageFont.load_default()
    if colour:
        d.rounded_rectangle((20, 20, 580, 280), 40, fill=(30, 90, 200)); d.text((70, 60), "ZEIM", font=f, fill=(240, 200, 30))
    else:
        d.text((60, 60), "ZEIM", font=f, fill="black"); d.ellipse((470, 30, 580, 140), outline="black", width=18)
    im.save(path)


def wait(pg, js, timeout=60000):
    """Poll a JS expression (the page's CSP forbids string eval in wait_for_function)."""
    import time
    end = time.time() + timeout / 1000
    while time.time() < end:
        if pg.evaluate(f"() => !!({js})"):
            return True
        pg.wait_for_timeout(250)
    raise TimeoutError(js)


def shot(pg, name):
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True); pg.screenshot(path=os.path.join(SHOTS, name), full_page=False)


def build(pg, out, name):
    pg.click(f"#tOut label:has(input[value={out}])")
    pg.wait_for_timeout(300)
    pg.evaluate("document.querySelector('#stats').innerHTML=''")
    pg.click("#btnBuild")
    wait(pg, "document.querySelector('#stats').textContent.includes('watertight')")
    st = pg.inner_text("#stats")
    ok(f"{name}: {out} builds, watertight, labelled", "✔ watertight" in st and "Logo & Drawing" in st, st)
    pg.wait_for_timeout(800)
    pg.locator("#viewer").scroll_into_view_if_needed()
    shot(pg, f"result-{out}.png")


def run(name, launch, bw, col):
    try: b = launch()
    except Exception as e: print(f"SKIP {name}: {str(e).splitlines()[0][:80]}"); return
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    pg.goto(URL + "/#cad"); pg.wait_for_timeout(800)
    ok(f"{name}: the CAD tab links to the tool", pg.is_visible("#cadTrace")); pg.click("#cadTrace"); pg.wait_for_timeout(600)
    card = pg.locator("#modeCards label[data-mode=trace2d]")
    ok(f"{name}: the Create flow has a 'Logo & Drawing to 3D' card", card.count() == 1 and "Logo & Drawing to 3D" in card.inner_text())
    card.click()
    ok(f"{name}: the CAD shortcut picked the card", pg.evaluate("document.querySelector('#modeCards input[value=trace2d]').checked"))
    ok(f"{name}: its settings panel shows", pg.is_visible("#traceOpts"))
    # every visible control has a label, and tap targets are at least 44 px
    unl = pg.evaluate("""[...document.querySelectorAll('#traceOpts input,#traceOpts select')].filter(e=>e.offsetParent&&e.type!=='radio'&&!(e.labels&&e.labels.length)).map(e=>e.id)""")
    ok(f"{name}: every setting has a label", not unl, unl)
    small = pg.evaluate("""[...document.querySelectorAll('#tOut label,#traceOpts .chk label,#traceOpts select,#traceOpts input[type=number],#traceOpts input[type=range]')].filter(e=>e.offsetParent).filter(e=>e.getBoundingClientRect().height<43.5).map(e=>e.id||e.textContent.trim())""")
    ok(f"{name}: tap targets are 44 px tall", not small, small)
    pg.focus("#tOut input[value=extrude]"); pg.keyboard.press("ArrowRight")
    ok(f"{name}: arrow keys move between outputs", pg.evaluate("document.querySelector('#tOut input:checked').value") == "cutter")
    pg.keyboard.press("ArrowLeft")
    pg.check("#sAck"); pg.set_input_files("#sFile", bw)
    wait(pg, "document.querySelector('#tracePrev svg')")
    wait(pg, "/hole/.test(document.querySelector('#traceStatus').textContent)")
    ok(f"{name}: live traced outline keeps the holes in the letters", "hole" in pg.inner_text("#traceStatus"), pg.inner_text("#traceStatus"))
    wait(pg, "document.querySelector('#stats').textContent.includes('watertight')")   # Beginner builds at once
    pg.locator("#traceOpts").scroll_into_view_if_needed(); shot(pg, "tool.png")
    pg.select_option("#t_base", "rounded"); pg.check("#t_keyring")
    build(pg, "extrude", name)
    build(pg, "cutter", name)
    build(pg, "stamp", name)
    pg.check("#sAck"); pg.set_input_files("#sFile", col); pg.wait_for_timeout(500)
    build(pg, "layers", name)
    ok(f"{name}: colour layers list the colour heights", "Colour" in pg.inner_text("#autoTable"), pg.inner_text("#autoTable"))
    pg.click("#btnSendSlicer"); pg.wait_for_timeout(1500)
    ok(f"{name}: the result opens in the FDM Slicer like other builds", "#slicer" in pg.url or "#edit" in pg.url, pg.url)
    shot(pg, "result-in-editor.png")
    b.close()
    if not bad: print(f"PASS {name}")


d = tempfile.mkdtemp(prefix="zeim-2d3d-")
bw, col = os.path.join(d, "logo.png"), os.path.join(d, "logo-colour.png"); logo(bw); logo(col, True)
with sync_playwright() as p:
    run("chrome", lambda: p.chromium.launch(), bw, col)
    SHOTS = None
    run("webkit", lambda: p.webkit.launch(), bw, col)
sys.exit(1 if bad else 0)
