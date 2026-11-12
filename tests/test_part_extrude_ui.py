"""The multi-extruder label is on screen, and the slot controls do not overlap.

Checked at 360, 390, 768 and 1280 px. A slice of two parts on slots 1 and 2
shows the same label on the result. Skipped when Playwright or Chrome is missing.
Nothing here sends a print.
"""
import os
import socket
import subprocess
import sys
import tempfile
import time

import pytest

from app.core.partslots import PRINT_NOTE
from tests.test_mesh_parts import _3mf, _box, _mesh_xml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABEL = "Not yet tested on a printer."
WIDTHS = ((360, 800), (390, 844), (768, 1024), (1280, 900))
try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None


def _two_part_3mf():
    left = _box((10, 10, 10), (0, 0, 5))
    right = _box((10, 10, 10), (40, 0, 5))
    return _3mf(
        [_mesh_xml(left, 1, "Left"), _mesh_xml(right, 2, "Right")],
        ['<item objectid="1"/>', '<item objectid="2"/>'],
    )


def _browser_ready():
    if sync_playwright is None:
        return False
    for path in ("/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/local/bin/google-chrome"):
        if os.path.exists(path):
            return True
    try:
        with sync_playwright() as p:
            return os.path.exists(p.chromium.executable_path)
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _browser_ready(), reason="needs Playwright and Chrome or Chromium")


def _launch(p):
    exe = getattr(p.chromium, "executable_path", "") or ""
    if exe and os.path.exists(exe):
        return p.chromium.launch()
    for path in ("/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/local/bin/google-chrome"):
        if os.path.exists(path):
            return p.chromium.launch(executable_path=path)
    return p.chromium.launch(channel="chrome")


def _wait(page, js, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        if page.evaluate("() => " + js):
            return
        page.wait_for_timeout(200)
    raise TimeoutError(js)


def _on_screen(page, selector):
    return page.evaluate(
        """(sel) => {
          const el = document.querySelector(sel);
          if (!el) return false;
          const style = getComputedStyle(el);
          const box = el.getBoundingClientRect();
          if (el.hidden || style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0) return false;
          if (box.width < 8 || box.height < 8) return false;
          const viewW = window.innerWidth, viewH = window.innerHeight;
          return box.top < viewH && box.bottom > 0 && box.left < viewW && box.right > 0;
        }""",
        selector,
    )


def _reveal(page, selector):
    page.evaluate(
        """(sel) => {
          const el = document.querySelector(sel);
          if (el) el.scrollIntoView({block: "center", inline: "nearest"});
        }""",
        selector,
    )
    page.wait_for_timeout(150)


def _overlaps(page, root):
    """Pairs of visible controls in root whose boxes cross. A control inside another is not a pair."""
    return page.evaluate(
        """(rootSel) => {
          const root = document.querySelector(rootSel);
          if (!root) return [["missing", rootSel]];
          const nodes = [...root.querySelectorAll("button, input, select, a, p.help, legend")].filter(el => {
            if (el.closest("[hidden], #gcPrev, .openin-steps, .slicers, details")) return false;
            const style = getComputedStyle(el);
            if (style.display === "none" || style.visibility === "hidden") return false;
            const box = el.getBoundingClientRect();
            return box.width > 2 && box.height > 2;
          });
          const hits = [];
          for (let i = 0; i < nodes.length; i++) {
            for (let j = i + 1; j < nodes.length; j++) {
              if (nodes[i].contains(nodes[j]) || nodes[j].contains(nodes[i])) continue;
              const a = nodes[i].getBoundingClientRect();
              const b = nodes[j].getBoundingClientRect();
              const ox = Math.min(a.right, b.right) - Math.max(a.left, b.left);
              const oy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
              if (ox > 4 && oy > 4) {
                const name = (el) => (el.id || el.getAttribute("aria-label") || (el.textContent || "").trim()).slice(0, 60);
                hits.push([name(nodes[i]), name(nodes[j]), Math.round(ox), Math.round(oy)]);
              }
            }
          }
          return hits;
        }""",
        root,
    )


@pytest.fixture(scope="module")
def base():
    while True:
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        if port not in (8765, 8791):
            break
    folder = tempfile.mkdtemp(prefix="zeim-multi-ui-")
    env = {**os.environ, "PORT": str(port), "HOST": "127.0.0.1", "PHOTO3D_DATA": folder + "/d",
           "PHOTO3D_OUT": folder + "/o", "PHOTO3D_MODE": "local"}
    logf = open(folder + "/server.log", "w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-m", "app.serve"], cwd=ROOT, env=env, stdout=logf, stderr=subprocess.STDOUT)
    up = False
    for _ in range(160):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.3).close()
            up = True
            break
        except OSError:
            if proc.poll() is not None:
                break
            time.sleep(0.25)
    if not up:
        logf.flush()
        err = open(folder + "/server.log", encoding="utf-8", errors="replace").read()[-2000:]
        proc.terminate()
        raise RuntimeError("server did not start\n" + err)
    yield f"http://127.0.0.1:{port}"
    proc.terminate()
    try:
        proc.wait(20)
    except subprocess.TimeoutExpired:
        proc.kill()
    logf.close()


def test_label_and_layout_at_four_widths(base):
    folder = tempfile.mkdtemp(prefix="zeim-multi-file-")
    path = os.path.join(folder, "apart.3mf")
    with open(path, "wb") as fh:
        fh.write(_two_part_3mf())
    os.makedirs("/opt/cursor/artifacts", exist_ok=True)
    with sync_playwright() as p:
        browser = _launch(p)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.add_init_script(
            "localStorage.setItem('zeim.printer', JSON.stringify({printer_id: 'bambu_x1c', nozzle: 0.4}))"
        )
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.goto(base + "/#slicer", wait_until="domcontentloaded")
        page.wait_for_selector("#editFile", state="attached", timeout=20000)
        page.set_input_files("#editFile", path)
        _wait(page, "document.querySelectorAll('#bedPartsList [data-part]').length >= 2", timeout=90)
        _reveal(page, "#bedParts")
        page.locator("#bedParts").click()
        page.wait_for_timeout(200)
        _wait(page, "document.querySelectorAll('#bedSlotPick button').length >= 2", timeout=30)
        page.locator("#bedPartsList [data-part]").nth(1).click()
        page.locator("#bedSlotPick button[data-slot='2']").click()
        _wait(page, "document.querySelector('#bedPartsPrint') && !document.querySelector('#bedPartsPrint').hidden")
        assert LABEL in PRINT_NOTE
        for width, height in WIDTHS:
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(250)
            where = f"{width}x{height}"
            _reveal(page, "#bedParts")
            if not _on_screen(page, "#partsSheet"):
                page.locator("#bedParts").click()
                page.wait_for_timeout(200)
            _reveal(page, "#bedPartsPrint")
            assert _on_screen(page, "#bedPartsPrint"), f"{where}: slot note is not on screen"
            assert LABEL in page.locator("#bedPartsPrint").inner_text()
            hits = _overlaps(page, "#partsSheet")
            assert hits == [], f"{where}: overlapping controls {hits}"
        page.set_viewport_size({"width": 1280, "height": 900})
        _reveal(page, "#partsSheet")
        page.screenshot(path="/opt/cursor/artifacts/slot-editor-1280.png")
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(200)
        _reveal(page, "#bedPartsPrint")
        page.screenshot(path="/opt/cursor/artifacts/slot-editor-390.png")
        page.set_viewport_size({"width": 1280, "height": 900})
        page.locator("#partsClose").click()
        page.locator("#bedPin").click()
        page.wait_for_timeout(200)
        _reveal(page, "#slicerBar [data-bed-cat=process]")
        page.locator("#slicerBar [data-bed-cat=process]").click()
        page.wait_for_timeout(200)
        _reveal(page, "#bedTools [data-bed-tab=quality]")
        page.locator("#bedTools [data-bed-tab=quality]").click()
        page.wait_for_timeout(300)
        _wait(page, "document.querySelector('#spGo') && !document.querySelector('#spGo').disabled", timeout=30)
        _reveal(page, "#spGo")
        page.locator("#spGo").click()
        _wait(page, "document.querySelector('#spMultiNote')", timeout=180)
        assert LABEL in page.locator("#spMultiNote").inner_text()
        assert "Left" in page.locator("#spPartExtruders").inner_text()
        assert "Right" in page.locator("#spPartExtruders").inner_text()
        for width, height in WIDTHS:
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(250)
            where = f"result {width}x{height}"
            _reveal(page, "#spMultiNote")
            assert _on_screen(page, "#spMultiNote"), f"{where}: label is not on screen"
            assert LABEL in page.locator("#spMultiNote").inner_text()
            hits = _overlaps(page, "#spOut")
            assert hits == [], f"{where}: overlapping controls {hits}"
        page.set_viewport_size({"width": 1280, "height": 900})
        _reveal(page, "#spMultiNote")
        page.screenshot(path="/opt/cursor/artifacts/slice-result-1280.png")
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(200)
        _reveal(page, "#spMultiNote")
        page.screenshot(path="/opt/cursor/artifacts/slice-result-390.png")
        href = page.locator("#editOpenCad").get_attribute("href")
        assert href
        page.goto(base + href, wait_until="domcontentloaded")
        page.wait_for_selector("#tabItems", timeout=20000)
        _wait(page, "document.querySelectorAll('#cwItems [data-part]').length >= 2", timeout=60)
        for width, height in WIDTHS:
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(300)
            page.locator("#tabItems").click()
            page.wait_for_timeout(300)
            where = f"CAD {width}x{height}"
            _reveal(page, "#cwItems")
            assert LABEL in page.locator("#cwItems").inner_text(), where
            hits = _overlaps(page, "#cwItems")
            assert hits == [], f"{where}: overlapping controls {hits}"
        assert errors == [], errors
        browser.close()
