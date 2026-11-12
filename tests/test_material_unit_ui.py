"""Multi-material unit picker and the slot editor, on a phone and on a desktop.

K1 with no unit shows the unit note. K1 with a CFS-C shows four filament slots.
Unit counts stop at the documented maximum. A control counts only when it is
painted inside the viewport.
"""
import os
import socket
import subprocess
import sys
import tempfile
import time

import pytest

from app.core.partslots import UNIT_NOTE

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None


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
VIEWPORTS = ((390, 844), (1280, 900))


def _launch(p):
    exe = getattr(p.chromium, "executable_path", "") or ""
    if exe and os.path.exists(exe):
        return p.chromium.launch()
    for path in ("/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/local/bin/google-chrome"):
        if os.path.exists(path):
            return p.chromium.launch(executable_path=path)
    return p.chromium.launch(channel="chrome")


def _wait(page, js, timeout=60):
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
          return box.top < viewH && box.bottom > 0 && box.left >= -1 && box.right <= viewW + 1;
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
    page.wait_for_timeout(200)


def _see(page, selector, where):
    _reveal(page, selector)
    assert _on_screen(page, selector), f"{where}: {selector} is not on screen"


def _no_overflow(page, where):
    width, inner = page.evaluate("[document.documentElement.scrollWidth, innerWidth]")
    assert width <= inner + 1, f"{where}: horizontal overflow {width} > {inner}"


@pytest.fixture(scope="module")
def base():
    while True:
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        if port not in (8765, 8791):
            break
    folder = tempfile.mkdtemp(prefix="zeim-unit-ui-")
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


def _options(page, selector):
    return page.eval_on_selector_all(selector + " option", "nodes => nodes.map(n => n.value)")


def test_unit_picker_is_on_screen_and_caps_the_count(base):
    with sync_playwright() as p:
        browser = _launch(p)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.goto(base + "/#account", wait_until="domcontentloaded")
        _wait(page, "document.querySelector('#ap_unit') && document.querySelector('#ap_unit').options.length > 1")
        for width, height in VIEWPORTS:
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(300)
            where = f"{width}x{height}"
            page.select_option("#ap_pr", "creality_k1")
            page.wait_for_timeout(150)
            assert page.input_value("#ap_unit") == "none"
            assert page.locator("#ap_ucf").get_attribute("hidden") is not None
            note = page.locator("#ap_unote").inner_text()
            assert UNIT_NOTE in note and "CFS-C" in note
            for sel in ("#ap_unit", "#ap_unote", "#ap_pr"):
                _see(page, sel, where)
            box = page.locator("#ap_unit").bounding_box()
            assert box and box["height"] >= 44, f"{where}: unit picker is under 44px {box}"
            _no_overflow(page, where)
            page.select_option("#ap_unit", "cfs_c")
            page.wait_for_timeout(100)
            assert "CFS-C: 4 slots." in page.locator("#ap_unote").inner_text()
            assert page.locator("#ap_ucf").get_attribute("hidden") is not None
            _see(page, "#ap_unote", where)
            page.select_option("#ap_pr", "creality_k2")
            page.wait_for_timeout(150)
            page.select_option("#ap_unit", "cfs")
            page.wait_for_timeout(100)
            assert _options(page, "#ap_uc") == ["1", "2", "3", "4"]
            _see(page, "#ap_uc", where)
            page.select_option("#ap_pr", "bambu_h2s")
            page.wait_for_timeout(150)
            page.select_option("#ap_unit", "ams_ht")
            page.wait_for_timeout(100)
            assert _options(page, "#ap_uc") == [str(n) for n in range(1, 9)]
            page.select_option("#ap_pr", "bambu_a1")
            page.wait_for_timeout(150)
            assert page.input_value("#ap_unit") == "ams_lite"
            assert page.locator("#ap_ucf").get_attribute("hidden") is not None
            page.select_option("#ap_unit", "ams")
            page.wait_for_timeout(100)
            assert _options(page, "#ap_uc") == ["1", "2", "3", "4"]
            _no_overflow(page, where)
        assert errors == [], errors
        browser.close()


def test_k1_cfs_c_shows_four_slots_and_none_shows_the_unit_note(base):
    with sync_playwright() as p:
        browser = _launch(p)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.add_init_script(
            "localStorage.setItem('zeim.printer', JSON.stringify({printer_id:'creality_k1', nozzle:0.4, unit_id:'cfs_c', unit_count:1}))"
        )
        page.goto(base + "/#slicer", wait_until="domcontentloaded")
        page.wait_for_selector("#editSample", state="visible", timeout=20000)
        page.click("#editSample")
        _wait(page, "document.querySelector('#viewEdit').classList.contains('has-model') && document.querySelector('#bedSlotPick button')", timeout=90)
        for width, height in VIEWPORTS:
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(300)
            where = f"CFS-C {width}x{height}"
            _reveal(page, "#bedParts")
            page.locator("#bedParts").click()
            page.wait_for_timeout(200)
            assert page.locator("#bedSlotPick button").count() == 4
            _see(page, "#bedSlotPick button", where)
            page.locator("#partsClose").click()
            page.locator("#bedPin").click()
            _reveal(page, "#bedFilament")
            page.locator("#bedFilament").click()
            page.locator("#bedTools [data-bed-tab=filament]").click()
            page.wait_for_timeout(200)
            assert page.locator("#spSlots .spslot").count() == 4
            assert page.locator("#spUnitNote").count() == 0
            _see(page, "#spSlots .spslot", where)
            _no_overflow(page, where)
            page.locator("#processClose").click()
            page.locator("#bedPin").click()
        page.evaluate(
            """async () => {
              const m = await import('/static/printer.js');
              await m.savePref({printer_id:'creality_k1', nozzle:0.4, unit_id:'none', unit_count:1});
            }"""
        )
        page.wait_for_timeout(400)
        for width, height in VIEWPORTS:
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(200)
            where = f"None {width}x{height}"
            _reveal(page, "#bedParts")
            page.locator("#bedParts").click()
            page.wait_for_timeout(200)
            assert page.locator("#bedSlotPick button").count() == 0
            assert UNIT_NOTE in page.locator("#bedPartsUnit").inner_text()
            _see(page, "#bedPartsUnit", where)
            page.locator("#partsClose").click()
            page.locator("#bedPin").click()
            _reveal(page, "#bedFilament")
            page.locator("#bedFilament").click()
            page.locator("#bedTools [data-bed-tab=filament]").click()
            page.wait_for_timeout(200)
            assert page.locator("#spSlots").count() == 0
            assert UNIT_NOTE in page.locator("#spUnitNote").inner_text()
            _see(page, "#spUnitNote", where)
            _no_overflow(page, where)
            page.locator("#processClose").click()
            page.locator("#bedPin").click()
        assert errors == [], errors
        browser.close()
