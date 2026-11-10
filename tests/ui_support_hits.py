"""Clicks land on the surface under the cursor.

TorchC0 green and red marks, and FDM support paint, at desktop and phone widths.
python tests/ui_support_hits.py URL
"""
import os
import sys
import tempfile

import trimesh
from PIL import Image
from playwright.sync_api import sync_playwright

URL = sys.argv[1].rstrip("/")
SHOTS = sys.argv[2] if len(sys.argv) > 2 else tempfile.gettempdir()
bad = []


def ok(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name, "" if cond else extra)
    if not cond:
        bad.append(name)


def box_stl(folder):
    path = os.path.join(folder, "box-20x16x12.stl")
    trimesh.creation.box(extents=[20, 16, 12]).apply_translation([0, 0, 6]).export(path)
    return path


def centroid(path, box, pred):
    im = Image.open(path).convert("RGB")
    pix = im.load()
    xs, ys = [], []
    x0, y0 = max(0, int(box["x"])), max(0, int(box["y"]))
    x1 = min(im.size[0], int(box["x"] + box["width"]))
    y1 = min(im.size[1], int(box["y"] + box["height"]))
    for y in range(y0, y1):
        for x in range(x0, x1):
            if pred(pix[x, y]):
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return (sum(xs) / len(xs), sum(ys) / len(ys), len(xs))


def marker_css(page, path, host, pred):
    page.screenshot(path=path)
    scale = page.evaluate("() => window.devicePixelRatio || 1")
    found = centroid(path, {
        "x": host["x"] * scale, "y": host["y"] * scale,
        "width": host["width"] * scale, "height": host["height"] * scale,
    }, pred)
    if not found:
        return None
    return (found[0] / scale, found[1] / scale, found[2])


def near(a, b, tol):
    return a is not None and abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def nums(page, name):
    raw = page.get_attribute("#rzPickView", name) or ""
    return [float(x) for x in raw.split(",") if x]


def canvas_matches(page, host_sel, canvas_sel):
    return page.evaluate("""([h, c]) => {
      const host = document.querySelector(h);
      const canvas = document.querySelector(c);
      const hr = host.getBoundingClientRect();
      const cr = canvas.getBoundingClientRect();
      return {
        dw: Math.abs(cr.width - hr.width), dh: Math.abs(cr.height - hr.height),
        bw: canvas.width, bh: canvas.height, cw: cr.width, ch: cr.height,
      };
    }""", [host_sel, canvas_sel])


def ray_gap(page, root):
    return page.evaluate("""(sel) => {
      const el = document.querySelector(sel);
      const cursor = (el.dataset.cursor || el.dataset.paintCursor || '').split(',').map(Number);
      const ray = (el.dataset.ray || el.dataset.paintRay || '').split(',').map(Number);
      if (cursor.length < 2 || ray.length < 2) return null;
      return Math.hypot(cursor[0] - ray[0], cursor[1] - ray[1]);
    }""", root)


def nums_attr(page, sel, name):
    raw = page.get_attribute(sel, name) or ""
    return [float(x) for x in raw.split(",") if x]


def place_resin(page, label):
    page.goto(URL + "/#torchc0")
    page.wait_for_selector("#rzFile", timeout=20000)
    page.set_input_files("#rzFile", BOX)
    page.wait_for_selector("#rzPickView canvas", timeout=30000)
    page.wait_for_function("() => !document.querySelector('#rzSupEdit').hidden", timeout=20000)
    page.wait_for_timeout(350)
    host = page.locator("#rzPickView").bounding_box()
    fit = canvas_matches(page, "#rzPickView", "#rzPickView canvas")
    ok(f"{label}: canvas fills the resin view", fit["dw"] < 2 and fit["dh"] < 2, str(fit))
    spots = (("top", 0.50, 0.36, "add"), ("side", 0.50, 0.62, "avoid"))
    for name, fx, fy, mode in spots:
        page.evaluate("document.getElementById('rzSupReset').click()")
        page.wait_for_timeout(150)
        page.evaluate("id => document.getElementById(id).click()", "rzModeAdd" if mode == "add" else "rzModeAvoid")
        x, y = host["x"] + host["width"] * fx, host["y"] + host["height"] * fy
        page.mouse.click(x, y)
        page.wait_for_timeout(400)
        kind = "supports" if mode == "add" else "avoid"
        hit = page.get_attribute("#rzPickView", f"data-{kind}") == "1"
        ok(f"{label}: {name} click hit the model", hit, page.inner_text("#rzSupStatus")[:180])
        if not hit:
            continue
        gap = ray_gap(page, "#rzPickView")
        ok(f"{label}: {name} ray meets the cursor", gap is not None and gap < 2.5, f"gap={gap}")
        contact = nums_attr(page, "#rzPickView", "data-contact")
        tap = nums_attr(page, "#rzPickView", "data-tap")
        world = max(abs(a - b) for a, b in zip(contact, tap)) if len(contact) == len(tap) == 3 else 99
        ok(f"{label}: {name} mark is the tapped point", world < 0.05 and page.get_attribute("#rzPickView", "data-moved") == "0", f"{contact} vs {tap}")
        pred = (lambda p: p[1] > 160 and p[1] > p[0] + 40 and p[1] > p[2] + 20) if mode == "add" else (lambda p: p[0] > 180 and p[0] > p[1] + 40 and p[0] > p[2] + 40)
        shot = os.path.join(SHOTS, f"hit-{label}-{name}.png")
        mark = marker_css(page, shot, host, pred)
        ok(f"{label}: {name} mark is on the click", near(mark, (x, y), 12), f"click={(x, y)} mark={mark}")
        if name == "side":
            world_before = page.get_attribute("#rzPickView", "data-contact")
            page.locator("#rzPickView").scroll_into_view_if_needed()
            page.click("#rzModeOrbit")
            view = page.locator("#rzPickView canvas").bounding_box()
            page.mouse.move(view["x"] + view["width"] * 0.35, view["y"] + view["height"] * 0.45)
            page.mouse.down()
            page.mouse.move(view["x"] + view["width"] * 0.7, view["y"] + view["height"] * 0.3, steps=8)
            page.mouse.up()
            page.wait_for_timeout(200)
            ok(f"{label}: mark stays put while orbiting", page.get_attribute("#rzPickView", "data-contact") == world_before, world_before)
            page.locator("#rzPickView").scroll_into_view_if_needed()
            page.wait_for_timeout(150)
            view = page.locator("#rzPickView canvas").bounding_box()
            again = marker_css(page, os.path.join(SHOTS, f"hit-{label}-orbit.png"), view, pred)
            ok(f"{label}: mark is still drawn after orbit", again is not None and again[2] > 8, str(again))


def place_paint(page, label):
    page.goto(URL + "/#slicer")
    page.wait_for_selector("#editFile", timeout=20000)
    page.set_input_files("#editFile", BOX)
    page.wait_for_selector("#editViewer canvas", timeout=30000)
    page.wait_for_selector("#procTab-support", state="attached", timeout=20000)
    page.click("#slicerBar [data-bed-cat=process]")
    page.click("#bedTools [data-bed-tab=support]")
    page.wait_for_function("() => document.getElementById('viewEdit').classList.contains('support-live')", timeout=8000)
    page.wait_for_selector("#spPaintNeed", timeout=8000)
    page.wait_for_timeout(250)
    cover = page.evaluate("""() => {
      const view = document.querySelector('#editViewer').getBoundingClientRect();
      const sheet = document.querySelector('#processSheet').getBoundingClientRect();
      const dock = document.querySelector('#spPaintDock').getBoundingClientRect();
      const cx = view.x + view.width / 2, cy = view.y + view.height / 2;
      const inside = (r, x, y) => x >= r.left && x <= r.right && y >= r.top && y <= r.bottom;
      const overlap = (a, b) => {
        const w = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left));
        const h = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
        return w * h;
      };
      return {
        centerCovered: inside(sheet, cx, cy),
        sheetOverlap: overlap(view, sheet),
        viewArea: view.width * view.height,
        dockCenter: inside(dock, cx, cy),
        sheet: {x: sheet.x, y: sheet.y, w: sheet.width, h: sheet.height},
        view: {x: view.x, y: view.y, w: view.width, h: view.height},
      };
    }""")
    ok(f"{label}: support sheet does not cover the model centre", not cover["centerCovered"], str(cover))
    ok(f"{label}: support sheet overlap stays small", cover["sheetOverlap"] < cover["viewArea"] * 0.08, str(cover))
    ok(f"{label}: paint tools do not cover the model centre", not cover["dockCenter"], str(cover))
    fit = canvas_matches(page, "#editViewer", "#editViewer canvas")
    ok(f"{label}: canvas fills the slicer view", fit["dw"] < 2 and fit["dh"] < 2, str(fit))
    page.click("#spPaintNever")
    page.wait_for_timeout(100)
    host = page.locator("#editViewer").bounding_box()
    x, y = host["x"] + host["width"] * 0.62, host["y"] + host["height"] * 0.45
    page.mouse.click(x, y)
    page.wait_for_timeout(250)
    gap = ray_gap(page, "#editViewer")
    ok(f"{label}: paint ray meets the cursor", gap is not None and gap < 2.5, f"gap={gap}")
    world = page.get_attribute("#editViewer", "data-paint")
    shot = os.path.join(SHOTS, f"paint-{label}.png")
    mark = marker_css(page, shot, host, lambda p: p[0] > 180 and p[0] > p[1] + 60 and p[0] > p[2] + 40)
    ok(f"{label}: red paint is on the click", near(mark, (x, y), 14), f"click={(round(x,1), round(y,1))} mark={mark} world={world}")
    page.click("#processClose")
    page.wait_for_function("() => !document.getElementById('viewEdit').classList.contains('support-live')", timeout=5000)
    page.click("#spPaintClear")
    page.wait_for_timeout(200)
    host2 = page.locator("#editViewer").bounding_box()
    x2, y2 = host2["x"] + host2["width"] * 0.58, host2["y"] + host2["height"] * 0.4
    page.mouse.click(x2, y2)
    page.wait_for_timeout(200)
    gap2 = ray_gap(page, "#editViewer")
    ok(f"{label}: paint still meets the cursor after Done", gap2 is not None and gap2 < 2.5, f"gap={gap2}")
    mark2 = marker_css(page, os.path.join(SHOTS, f"paint-done-{label}.png"), host2, lambda p: p[0] > 180 and p[0] > p[1] + 60 and p[0] > p[2] + 40)
    ok(f"{label}: red paint is on the click after Done", near(mark2, (x2, y2), 14), f"click={(round(x2,1), round(y2,1))} mark={mark2}")


BOX = box_stl(tempfile.mkdtemp(prefix="zeim-hit-"))
with sync_playwright() as p:
    browser = p.chromium.launch()
    for width, height, dpr in ((1280, 800, 1), (1280, 800, 2), (390, 844, 2)):
        tag = f"{width}-dpr{dpr}"
        page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=dpr)
        page.on("pageerror", lambda e, tag=tag: ok(f"{tag}: no page error", False, str(e)))
        place_resin(page, f"resin {tag}")
        place_paint(page, f"paint {tag}")
        page.close()
    browser.close()
print("\n".join(bad) or "ok")
sys.exit(1 if bad else 0)
