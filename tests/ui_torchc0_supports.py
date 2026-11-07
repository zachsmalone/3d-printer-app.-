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
    ok(f"{label}: green mark is the contact", "where the pillar will touch" in rule and "where the pillar will touch" in status, status)
    contact = [float(x) for x in (page.get_attribute("#rzPickView", "data-contact") or "").split(",") if x]
    tap = [float(x) for x in (page.get_attribute("#rzPickView", "data-tap") or "").split(",") if x]
    moved = page.get_attribute("#rzPickView", "data-moved")
    if moved == "1":
        ok(f"{label}: projected mark is below the tap", len(contact) == 3 and len(tap) == 3 and contact[2] < tap[2] - 0.3, f"{contact} vs {tap}")
        ok(f"{label}: projection is stated", "underside" in status.lower(), status)
    else:
        ok(f"{label}: mark stays on the tapped face", len(contact) == 3 and len(tap) == 3 and abs(contact[2] - tap[2]) < 0.45, f"{contact} vs {tap} {status}")
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


STL = None
folder = tempfile.mkdtemp(prefix="zeim-sup-")
STL = stl_path(folder)
with sync_playwright() as p:
    browser = p.chromium.launch()
    for width, height in ((1280, 900), (390, 844)):
        page = browser.new_page(viewport={"width": width, "height": height})
        run(page, f"chrome {width}", width)
        page.close()
    browser.close()
print("\n".join(bad) or "ok")
sys.exit(1 if bad else 0)
