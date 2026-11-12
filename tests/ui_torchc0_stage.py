"""TorchC0 result stage, plate fit, stale prepare, support markers, and the settings preview.
python tests/ui_torchc0_stage.py URL [SHOTDIR]
"""
import os
import sys
import tempfile

import trimesh
from playwright.sync_api import sync_playwright

URL = sys.argv[1].rstrip("/")
SHOT = sys.argv[2] if len(sys.argv) > 2 else tempfile.gettempdir()
os.makedirs(SHOT, exist_ok=True)
bad = []


def ok(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name, "" if cond else extra)
    if not cond:
        bad.append(name)


def box_of(page, sel):
    return page.evaluate(
        """sel => { const e = document.querySelector(sel); if (!e || e.hidden || !e.getClientRects().length) return null;
          const b = e.getBoundingClientRect(); return {x:b.left,y:b.top,r:b.right,b:b.bottom,w:b.width,h:b.height}; }""",
        sel,
    )


def overlaps(a, b):
    if not a or not b or a["w"] < 2 or b["w"] < 2 or a["h"] < 2 or b["h"] < 2:
        return False
    return a["x"] < b["r"] - 1 and b["x"] < a["r"] - 1 and a["y"] < b["b"] - 1 and b["y"] < a["b"] - 1


def stage_alive(page):
    return page.evaluate(
        """() => {
          const note = document.querySelector('#rzRun:not([hidden]), .rzStageNote:not([hidden])');
          const noteOn = !!(note && note.getClientRects().length && getComputedStyle(note).visibility !== 'hidden' && (note.innerText || '').trim());
          const views = ['#rzPickView', '#rzView'];
          for (const sel of views) {
            const el = document.querySelector(sel);
            if (!el || el.hidden) continue;
            const canvas = el.querySelector('canvas');
            const tris = Number(el.dataset.triangles || 0);
            if (canvas && tris > 0) return true;
          }
          return noteOn;
        }"""
    )


def open_settings(page):
    chip = page.locator("#zws-settings.zws-p.min .zws-chip")
    if chip.count() and chip.first.is_visible():
        chip.first.click()
        page.wait_for_timeout(200)


def prepare(page, hollow=False, supports=False):
    if page.is_checked("#rzHollow") != hollow:
        page.click("#rzHollow")
    if page.is_checked("#rzSup") != supports:
        page.click("#rzSup")
    samples = []
    page.click("#rzGo")
    for _ in range(80):
        samples.append(stage_alive(page))
        if page.locator("#torchOut a[href$='torchc0.stl']").count():
            break
        page.wait_for_timeout(250)
    page.wait_for_selector("#torchOut a[href$='torchc0.stl']", timeout=240000)
    samples.append(stage_alive(page))
    return samples


def layout(page, label):
    open_settings(page)
    page.wait_for_timeout(300)
    dock = box_of(page, "#rzPreviewDock")
    tools = box_of(page, "#rzTools")
    preview = box_of(page, "#rzPickView")
    ok(f"{label}: preview dock is on screen", dock and dock["h"] >= 120 and dock["w"] >= 120, dock)
    ok(f"{label}: tools sit under the preview", dock and tools and dock["b"] <= tools["y"] + 4, (dock, tools))
    hint = box_of(page, "#rzCamHint")
    ok(f"{label}: camera hint is a readable line", hint and hint["w"] >= 120 and hint["h"] < hint["w"], hint)
    narrow = page.evaluate(
        """() => [...document.querySelectorAll('#rzTools .help, #rzCamHint, #rzSupRule, #rzFileStatus')]
          .filter(e => e.getClientRects().length && !e.hidden && e.innerText.trim())
          .map(e => Math.round(e.getBoundingClientRect().width))
          .filter(w => w < 120)"""
    )
    ok(f"{label}: no text column under 120px", not narrow, narrow)
    panel = box_of(page, "#zws-settings")
    pill = box_of(page, "#saveInd")
    out = box_of(page, "#zws-out")
    go = box_of(page, "#torchGo")
    ok(f"{label}: settings panel misses the save pill", not overlaps(panel, pill), (panel, pill))
    ok(f"{label}: settings panel misses the result panel", not overlaps(panel, out), (panel, out))
    ok(f"{label}: save pill misses Prepare", not overlaps(pill, go), (pill, go))
    before = page.evaluate("() => document.querySelector('#rzTools').scrollTop")
    dock_before = dict(dock)
    page.evaluate("() => { const t = document.querySelector('#rzTools'); t.scrollTop = t.scrollHeight; }")
    page.wait_for_timeout(150)
    dock_after = box_of(page, "#rzPreviewDock")
    ok(f"{label}: preview stays while tools scroll",
       dock_after and abs(dock_after["y"] - dock_before["y"]) < 3 and dock_after["h"] > 80,
       (dock_before, dock_after, before))
    page.evaluate("() => { document.querySelector('#rzTools').scrollTop = 0; }")
    def drag_edge(direction):
        handle = page.locator(f"#zws-settings .zws-edge[data-dir={direction}]")
        if not handle.count():
            return None
        hb = handle.bounding_box()
        if not hb:
            return None
        if direction == "e":
            page.mouse.move(hb["x"] + 4, hb["y"] + min(30, hb["height"] / 2))
            page.mouse.down()
            page.mouse.move(hb["x"] - 70, hb["y"] + min(30, hb["height"] / 2), steps=6)
            page.mouse.up()
        else:
            page.mouse.move(hb["x"] + min(30, hb["width"] / 2), hb["y"] + 4)
            page.mouse.down()
            page.mouse.move(hb["x"] + min(30, hb["width"] / 2), hb["y"] - 90, steps=6)
            page.mouse.up()
        page.wait_for_timeout(300)
        return box_of(page, "#rzPickView")

    grown = drag_edge("e")
    changed = preview and grown and (abs(grown["w"] - preview["w"]) >= 16 or abs(grown["h"] - preview["h"]) >= 16)
    if not changed:
        grown = drag_edge("n") or grown
        changed = preview and grown and (abs(grown["w"] - preview["w"]) >= 16 or abs(grown["h"] - preview["h"]) >= 16)
    ok(f"{label}: preview resizes with the panel", changed, (preview, grown))
    cam = page.get_attribute("#rzPickView", "data-cam") or ""
    box = page.locator("#rzPickView").bounding_box()
    page.mouse.move(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.55)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] * 0.8, box["y"] + box["height"] * 0.3, steps=8)
    page.mouse.up()
    page.wait_for_timeout(200)
    cam2 = page.get_attribute("#rzPickView", "data-cam") or ""
    ok(f"{label}: orbit moves the preview camera", cam and cam2 and cam != cam2, (cam, cam2))
    page.screenshot(path=os.path.join(SHOT, f"torchc0-panel-{label}.png"))


def run(page, label, stl, yaw_stl, printer):
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.goto(URL + "/#torchc0")
    page.wait_for_selector("#rzFile", timeout=20000)
    if printer:
        page.select_option("#rzPrinter", printer)
    page.set_input_files("#rzFile", stl)
    open_settings(page)
    page.wait_for_selector("#rzPickView canvas", timeout=60000)
    page.wait_for_function("() => Number(document.querySelector('#rzPickView').dataset.triangles) > 0", timeout=20000)
    page.locator("#rzModeAdd").click()
    page.locator("#rzPickView").scroll_into_view_if_needed()
    page.wait_for_timeout(200)
    canvas = page.locator("#rzPickView canvas").first
    box = canvas.bounding_box()
    hit = False
    for fx, fy in ((0.5, 0.35), (0.5, 0.5), (0.42, 0.4), (0.62, 0.38), (0.38, 0.55), (0.55, 0.6), (0.3, 0.3)):
        if not box:
            break
        page.mouse.click(box["x"] + box["width"] * fx, box["y"] + box["height"] * fy)
        try:
            page.wait_for_function("() => Number(document.querySelector('#rzPickView').dataset.supports) >= 1", timeout=1500)
            hit = True
            break
        except Exception:
            continue
    if not hit:
        info = page.evaluate("""() => {
          const c = document.querySelector('#rzPickView canvas');
          const b = c ? c.getBoundingClientRect() : null;
          return { pressed: document.querySelector('#rzModeAdd').getAttribute('aria-pressed'),
            tris: document.querySelector('#rzPickView').dataset.triangles,
            status: document.querySelector('#rzSupStatus') && document.querySelector('#rzSupStatus').innerText,
            box: b && {w: b.width, h: b.height, y: b.top} };
        }""")
        print(f"MISS {label}", info)
    ok(f"{label}: support click hit the model", hit, info if not hit else "")
    if hit:
        gap = float(page.get_attribute("#rzPickView", "data-mark-gap") or "99")
        ok(f"{label}: marker sits on the surface", gap < 1.0, gap)
    samples = prepare(page, hollow=False, supports=True)
    ok(f"{label}: stage stayed occupied during prepare", all(samples), samples)
    page.screenshot(path=os.path.join(SHOT, f"torchc0-stage-{label}.png"))
    note = page.inner_text("#rzMeshNote")
    ok(f"{label}: mesh note does not pretend", "full resolution" not in note.lower(), note)
    if page.locator("#rzPickView").count():
        layout(page, label)
    open_settings(page)
    page.locator("#rzSupReset").scroll_into_view_if_needed()
    page.click("#rzSupReset")
    page.wait_for_timeout(400)
    stale = page.inner_text("#torchOut")
    ok(f"{label}: stale copy after erasing supports", "Supports changed. Prepare again to update." in stale, stale[:240])
    page.click("#rzSlice")
    page.wait_for_timeout(200)
    ok(f"{label}: slice asks for a new prepare", "Prepare again" in page.inner_text("#torchOut"))
    # A model that fits only when the bed's X and Y are swapped.
    page.set_input_files("#rzFile", yaw_stl)
    open_settings(page)
    page.wait_for_selector("#rzPickView canvas", timeout=60000)
    samples = prepare(page, hollow=False, supports=False)
    ok(f"{label}: yaw model stage stayed occupied", all(samples), samples)
    opts = page.locator("#rzPlate option").all_inner_texts()
    disabled = [t for t in opts if "does not fit" in t]
    note = page.inner_text("#rzPlateNote")
    ok(f"{label}: yaw-fit plate is not marked too big", not disabled and "does not fit" not in note, (opts, note))
    ok(f"{label}: no page errors", not errs, errs)


def yaw_box(folder):
    """70 x 140 x 8 mm. Fits a bed only after the X and Y axes are sorted."""
    path = os.path.join(folder, "yaw.stl")
    trimesh.creation.box(extents=[70, 140, 8]).apply_translation([0, 0, 4]).export(path)
    return path


def main():
    folder = tempfile.mkdtemp(prefix="torchc0-stage-")
    small = os.path.join(folder, "box.stl")
    trimesh.creation.box(extents=[24, 18, 12]).apply_translation([0, 0, 6]).export(small)
    yaw = yaw_box(folder)
    big = os.path.join(folder, "sphere.stl")
    sphere = trimesh.creation.uv_sphere(radius=30, count=[520, 580])
    assert len(sphere.faces) >= 600000, len(sphere.faces)
    sphere.apply_translation([0, 0, 30])
    sphere.export(big)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for label, size in (("1280", {"width": 1280, "height": 900}), ("390", {"width": 390, "height": 844})):
            context = browser.new_context(viewport=size)
            page = context.new_page()
            page.goto(URL + "/#torchc0")
            page.wait_for_selector("#rzPrinter", timeout=20000)
            picked = page.evaluate(
                """async () => {
                  const cat = await (await fetch('/api/resin/catalog')).json();
                  const plates = cat.lumen_plates || [];
                  const tol = 0.35;
                  for (const printer of cat.printers) {
                    const bed = printer.bed_mm;
                    if (!bed) continue;
                    for (const plate of plates) {
                      if ((plate.manufacturer || '').toLowerCase() !== (printer.brand || '').toLowerCase()) continue;
                      if (plate.name !== printer.model) continue;
                      const pb = [plate.build_width_um / 1000, plate.build_depth_um / 1000, plate.build_height_um / 1000];
                      if (!bed.every((v, i) => Math.abs(+v - pb[i]) <= tol)) continue;
                      const xy = [pb[0], pb[1]].slice().sort((a, b) => a - b);
                      if (xy[1] - xy[0] < 40) continue;
                      if (70 <= xy[0] + 1e-3 && 140 <= xy[1] + 1e-3 && 8 <= pb[2] + 1e-3) return printer.id;
                    }
                  }
                  return '';
                }"""
            )
            ok(f"{label}: found a yaw-fit printer", bool(picked), picked)
            run(page, label, small, yaw, picked)
            # Large mesh: the stage must not go blank while the preview downloads.
            page.set_input_files("#rzFile", big)
            open_settings(page)
            page.wait_for_selector("#rzPickView canvas", timeout=120000)
            samples = prepare(page, hollow=False, supports=False)
            ok(f"{label}: large model stage stayed occupied", all(samples), samples[-5:])
            page.screenshot(path=os.path.join(SHOT, f"torchc0-large-{label}.png"))
            context.close()
        # Forced download failure, desktop.
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        page.goto(URL + "/#torchc0")
        page.wait_for_selector("#rzFile", timeout=20000)
        page.set_input_files("#rzFile", small)
        page.wait_for_selector("#rzPickView canvas", timeout=60000)

        def abort_mesh(route):
            url = route.request.url
            if route.request.method == "GET" and (url.endswith("preview.stl") or url.endswith("torchc0.stl")):
                route.abort()
            else:
                route.continue_()

        page.route("**/*", abort_mesh)
        if page.is_checked("#rzHollow"):
            page.click("#rzHollow")
        if page.is_checked("#rzSup"):
            page.click("#rzSup")
        page.click("#rzGo")
        page.wait_for_selector("#rzView, .rzStageNote", timeout=120000)
        page.wait_for_timeout(500)
        text = page.evaluate(
            """() => [...document.querySelectorAll('.rzStageNote, #rzView')].map(e => e.innerText || '').join(' ')"""
        )
        ok("fetch failure shows in the stage", "did not load" in text.lower() or "preview" in text.lower(), text[:300])
        loaded = page.evaluate("() => document.querySelector('#rzView') && document.querySelector('#rzView').dataset.prepared")
        ok("fetch failure does not claim the preview loaded", loaded != "1", loaded)
        page.screenshot(path=os.path.join(SHOT, "torchc0-fetch-fail.png"))
        page.close()
        browser.close()


if __name__ == "__main__":
    main()
    sys.exit(1 if bad else 0)
