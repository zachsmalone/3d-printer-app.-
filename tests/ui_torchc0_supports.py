"""Place, erase, and keep-clear resin supports on the loaded model. python tests/ui_torchc0_supports.py URL"""
import os
import sys
import tempfile

import trimesh
from playwright.sync_api import sync_playwright

URL = sys.argv[1].rstrip("/")
SHOTS = sys.argv[2] if len(sys.argv) > 2 else tempfile.gettempdir()
bad = []


def ok(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name, "" if cond else extra)
    if not cond:
        bad.append(name)


def stl_path(folder):
    path = os.path.join(folder, "overhang.stl")
    base = trimesh.creation.box(extents=[16, 12, 4]).apply_translation([0, 0, 2])
    wing = trimesh.creation.box(extents=[8, 8, 4]).apply_translation([14, 0, 10])
    trimesh.util.concatenate([base, wing]).export(path)
    return path


def stay(page):
    dlg = page.locator("#dlgBedLeave[open]")
    if dlg.count():
        page.locator("#dlgBedLeave [data-leave=stay]").click()


def run(page, label, width):
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.goto(URL + "/#torchc0")
    page.wait_for_selector("#rzFile", timeout=20000)
    page.set_input_files("#rzFile", STL)
    page.wait_for_selector("#rzPickView canvas", timeout=30000)
    page.wait_for_function("() => !document.querySelector('#rzSupEdit').hidden", timeout=20000)
    page.wait_for_timeout(300)
    ok(f"{label}: model canvas", page.locator("#rzPickView canvas").count() == 1)
    ok(f"{label}: orbit is the default", page.get_attribute("#rzModeOrbit", "aria-pressed") == "true")
    page.click("#rzModeAdd")
    box = page.locator("#rzPickView canvas").bounding_box()
    if box["y"] < 40 or box["y"] + box["height"] > page.viewport_size["height"] - 20:
        page.evaluate("(dy) => window.scrollBy(0, dy)", box["y"] - 140)
        page.wait_for_timeout(150)
        box = page.locator("#rzPickView canvas").bounding_box()
    page.screenshot(path=os.path.join(SHOTS, f"torchc0-supports-before-{width}.png"))
    hit = False
    spot = (0.64, 0.42)
    for fx, fy in ((0.64, 0.42), (0.70, 0.38), (0.42, 0.62), (0.40, 0.55)):
        page.mouse.click(box["x"] + box["width"] * fx, box["y"] + box["height"] * fy)
        try:
            page.wait_for_function("() => Number(document.querySelector('#rzPickView').dataset.supports) >= 1", timeout=8000)
            hit = True
            spot = (fx, fy)
            break
        except Exception:
            continue
    ok(f"{label}: click hit the model", hit, page.inner_text("#rzSupStatus"))
    if not hit:
        return
    status = page.inner_text("#rzSupStatus")
    rule = page.inner_text("#rzSupRule")
    ok(f"{label}: green mark is the tapped point", "point you tapped" in rule and "point you tapped" in status, status)
    contact = [float(x) for x in (page.get_attribute("#rzPickView", "data-contact") or "").split(",") if x]
    tap = [float(x) for x in (page.get_attribute("#rzPickView", "data-tap") or "").split(",") if x]
    gap = max(abs(a - b) for a, b in zip(contact, tap)) if len(contact) == 3 and len(tap) == 3 else 99
    ok(f"{label}: mark stays on the tapped face", gap < 0.05 and page.get_attribute("#rzPickView", "data-moved") == "0", f"{contact} vs {tap} {status}")
    ok(f"{label}: one support marker", page.get_attribute("#rzPickView", "data-supports") == "1", status)
    page.screenshot(path=os.path.join(SHOTS, f"torchc0-supports-{width}.png"))
    before = page.get_attribute("#rzPickView", "data-supports")
    page.evaluate("document.getElementById('rzSupUndo').click()")
    page.wait_for_function("n => document.querySelector('#rzPickView').dataset.supports === '0' || document.querySelector('#rzPickView').dataset.supports < n", arg=before, timeout=5000)
    page.evaluate("document.getElementById('rzSupReset').click()")
    page.wait_for_function("() => document.querySelector('#rzPickView').dataset.supports === '0'", timeout=5000)
    page.evaluate("document.getElementById('rzModeAdd').click()")
    page.mouse.click(box["x"] + box["width"] * spot[0], box["y"] + box["height"] * spot[1])
    page.wait_for_function("() => Number(document.querySelector('#rzPickView').dataset.supports) >= 1", timeout=5000)
    page.evaluate("document.getElementById('rzModeAvoid').click()")
    avoided = False
    for dx, dy in ((28, 0), (-28, 16), (0, -24), (36, 18)):
        page.mouse.click(box["x"] + box["width"] * spot[0] + dx, box["y"] + box["height"] * spot[1] + dy)
        try:
            page.wait_for_function("() => document.querySelector('#rzPickView').dataset.avoid === '1'", timeout=8000)
            avoided = True
            break
        except Exception:
            continue
    ok(f"{label}: keep-clear click hit", avoided, page.inner_text("#rzSupStatus"))
    if not avoided:
        return
    ok(f"{label}: keep-clear marker", page.get_attribute("#rzPickView", "data-avoid") == "1")
    avoid_status = page.inner_text("#rzSupStatus")
    ok(f"{label}: keep-clear mark is the exclusion point", "keep-clear point" in avoid_status.lower(), avoid_status)
    page.click("#rzModeOrbit")
    page.mouse.move(box["x"] + 30, box["y"] + 40)
    page.mouse.down()
    page.mouse.move(box["x"] + 90, box["y"] + 80)
    page.mouse.up()
    ok(f"{label}: canvas still there after orbit drag", page.locator("#rzPickView canvas").count() == 1)
    if page.is_checked("#rzHollow"):
        page.click("#rzHollow")
    page.click("#rzGo")
    page.wait_for_selector("#torchOut a[href$='torchc0.stl']", timeout=180000)
    text = page.inner_text("#torchOut")
    ok(f"{label}: prepare kept the placed support", "Placed supports are built" in text or "support" in text.lower(), text[:400])
    ok(f"{label}: no page errors", not errs, errs)
    page.screenshot(path=os.path.join(SHOTS, f"torchc0-supports-prepared-{width}.png"))


def box_stl(folder):
    path = os.path.join(folder, "box-20x16x12.stl")
    trimesh.creation.box(extents=[20, 16, 12]).apply_translation([0, 0, 6]).export(path)
    return path


def colored_centroid(path, box, pred):
    from PIL import Image
    im = Image.open(path).convert("RGB")
    pix = im.load()
    xs, ys = [], []
    x0, y0 = int(box["x"]), int(box["y"])
    x1 = min(im.size[0], int(box["x"] + box["width"]))
    y1 = min(im.size[1], int(box["y"] + box["height"]))
    for y in range(max(0, y0), y1):
        for x in range(max(0, x0), x1):
            if pred(pix[x, y]):
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return (sum(xs) / len(xs), sum(ys) / len(ys), len(xs))


def run_jupiter(page, label, width):
    """Real TorchC0 page: nav, Jupiter, load. The page keeps the model on screen. Not a bare viewer."""
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.goto(URL + "/#torchc0")
    page.wait_for_selector("#rzFile", timeout=20000)
    page.select_option("#rzPrinter", label="ELEGOO Jupiter")
    page.set_input_files("#rzFile", BOX)
    page.wait_for_selector("#rzPickView canvas", timeout=30000)
    page.wait_for_function("() => !document.querySelector('#rzSupEdit').hidden", timeout=20000)
    page.wait_for_timeout(300)
    ok(f"{label}: Jupiter selected", page.locator("#rzPrinter option:checked").inner_text() == "ELEGOO Jupiter")
    page.wait_for_function("() => (document.querySelector('#rzFileStatus') || {}).textContent.includes('loaded')", timeout=20000)
    page.wait_for_timeout(250)
    def canvas_in_view():
        rect = page.locator("#rzPickView canvas").bounding_box()
        chrome = page.evaluate("() => { const b = document.querySelector('header.topbar'); return b ? b.getBoundingClientRect().bottom : 0; }")
        vh = page.viewport_size["height"]
        return rect, chrome, rect["y"] >= chrome - 2 and rect["y"] + rect["height"] <= vh + 2
    box, chrome, shown = canvas_in_view()
    ok(f"{label}: model stays on screen after load", shown, f"box={box} header={chrome}")
    if not shown:
        return
    shot = os.path.join(SHOTS, f"torchc0-jupiter-before-{width}.png")
    page.screenshot(path=shot)
    model = colored_centroid(shot, box, lambda p: 80 < p[0] < 200 and p[1] > 100 and p[2] > 140 and p[2] > p[0] + 25)
    ok(f"{label}: model is on the scrolled page", model is not None and model[2] > 400, str(box))
    if model is None:
        return
    page.evaluate("document.getElementById('rzModeAdd').click()")
    green = False
    for dy in (0, -24, 28, -48, 52):
        page.mouse.click(model[0], model[1] + dy)
        try:
            page.wait_for_function("() => Number(document.querySelector('#rzPickView').dataset.supports) >= 1 || (document.querySelector('#rzPickView').dataset.normal || '') !== ''", timeout=4000)
        except Exception:
            continue
        if page.get_attribute("#rzPickView", "data-normal"):
            try:
                page.wait_for_function("() => Number(document.querySelector('#rzPickView').dataset.supports) >= 1", timeout=8000)
                green = True
            except Exception:
                green = False
            break
        page.evaluate("document.querySelector('#rzPickView').dataset.normal = ''")
    status = page.inner_text("#rzSupStatus")
    ok(f"{label}: top tap placed a support", green, status + " normal=" + str(page.get_attribute("#rzPickView", "data-normal")))
    if green:
        ok(f"{label}: green mark is the tapped point", "point you tapped" in status.lower(), status)
        contact = [float(x) for x in page.get_attribute("#rzPickView", "data-contact").split(",")]
        tap = [float(x) for x in page.get_attribute("#rzPickView", "data-tap").split(",")]
        gap = max(abs(a - b) for a, b in zip(contact, tap))
        ok(f"{label}: green contact is the tap", gap < 0.05 and page.get_attribute("#rzPickView", "data-moved") == "0", f"{contact} vs {tap}")
        green_shot = os.path.join(SHOTS, f"torchc0-support-jupiter-{width}.png")
        page.screenshot(path=green_shot)
        vivid_green = colored_centroid(green_shot, box, lambda p: p[1] > 190 and p[1] > p[0] + 60 and p[1] > p[2] + 40)
        ok(f"{label}: green mark is clearly visible", vivid_green is not None and vivid_green[2] > 12, str(vivid_green))
    page.evaluate("document.getElementById('rzSupReset').click()")
    page.wait_for_function("() => document.querySelector('#rzPickView').dataset.supports === '0'", timeout=5000)
    page.evaluate("document.getElementById('rzModeAvoid').click()")
    box, chrome, shown = canvas_in_view()
    ok(f"{label}: model still on screen for keep-clear", shown, f"box={box} header={chrome}")
    if not shown:
        return
    page.screenshot(path=shot)
    model = colored_centroid(shot, box, lambda p: 80 < p[0] < 200 and p[1] > 100 and p[2] > 140 and p[2] > p[0] + 25)
    if model is None:
        ok(f"{label}: model still visible after the second scroll", False, str(box))
        return
    side = (model[0], min(box["y"] + box["height"] - 16, model[1] + 48))
    page.mouse.click(side[0], side[1])
    try:
        page.wait_for_function("() => document.querySelector('#rzPickView').dataset.avoid === '1' && document.querySelector('#rzPickView').dataset.kind === 'avoid'", timeout=5000)
        placed = True
    except Exception:
        placed = False
    status = page.inner_text("#rzSupStatus")
    ok(f"{label}: side tap placed a keep-clear mark", placed, status)
    if not placed:
        return
    normal = [float(x) for x in (page.get_attribute("#rzPickView", "data-normal") or "0,0,1").split(",")]
    ok(f"{label}: keep-clear hit a side face", abs(normal[2]) < 0.45, str(normal))
    contact = [float(x) for x in page.get_attribute("#rzPickView", "data-contact").split(",")]
    tap = [float(x) for x in page.get_attribute("#rzPickView", "data-tap").split(",")]
    gap = max(abs(a - b) for a, b in zip(contact, tap))
    ok(f"{label}: stored exclusion is the clicked point", gap < 0.05 and page.get_attribute("#rzPickView", "data-moved") == "0", f"{contact} vs {tap}")
    ok(f"{label}: keep-clear sentence does not say the mark moved", "underside" not in status.lower(), status)
    marked = os.path.join(SHOTS, f"torchc0-keepclear-jupiter-{width}.png")
    box = page.locator("#rzPickView canvas").bounding_box()
    page.screenshot(path=marked)
    red = colored_centroid(marked, box, lambda p: p[0] > 220 and p[0] > p[1] + 80 and p[0] > p[2] + 80)
    if red is None:
        ok(f"{label}: red mark is visible", False, status)
        return
    dx, dy = red[0] - side[0], red[1] - side[1]
    dist = (dx * dx + dy * dy) ** 0.5
    ok(f"{label}: red mark is on the click", dist < 16 and abs(dy) < 16, f"dx={dx:.1f} dy={dy:.1f} dist={dist:.1f} click={side} red={red[:2]}")
    ok(f"{label}: no page errors", not errs, errs)


STL = None
BOX = None
folder = tempfile.mkdtemp(prefix="zeim-sup-")
STL = stl_path(folder)
BOX = box_stl(folder)
with sync_playwright() as p:
    browser = p.chromium.launch()
    for width, height in ((1280, 900), (390, 844)):
        page = browser.new_page(viewport={"width": width, "height": height})
        run(page, f"chrome {width}", width)
        page.close()
        page = browser.new_page(viewport={"width": width, "height": height})
        run_jupiter(page, f"chrome {width} jupiter", width)
        page.close()
    browser.close()
print("\n".join(bad) or "ok")
sys.exit(1 if bad else 0)
