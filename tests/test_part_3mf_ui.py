"""Export from the FDM slicer carries the filament slots assigned on the parts sheet.

Phone and desktop. The sheet and the export dialog are unchanged; this only checks
the file that Download saves. Skipped when Playwright or Chrome is missing.
"""
import io
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import zipfile

import pytest

from tests.test_mesh_parts import _3mf, _box, _mesh_xml

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


def _launch(p):
    exe = getattr(p.chromium, "executable_path", "") or ""
    if exe and os.path.exists(exe):
        return p.chromium.launch()
    for path in ("/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/local/bin/google-chrome"):
        if os.path.exists(path):
            return p.chromium.launch(executable_path=path)
    return p.chromium.launch(channel="chrome")


def _apart() -> bytes:
    left = _box((10, 10, 10), (0, 0, 5))
    right = _box((10, 10, 10), (40, 0, 5))
    return _3mf(
        [_mesh_xml(left, 1, "Left"), _mesh_xml(right, 2, "Right")],
        ['<item objectid="1"/>', '<item objectid="2"/>'],
    )


def _on_screen(page, selector):
    return page.evaluate(
        """(sel) => {
          const el = document.querySelector(sel);
          if (!el) return false;
          const style = getComputedStyle(el);
          const box = el.getBoundingClientRect();
          if (el.hidden || style.display === "none" || style.visibility === "hidden") return false;
          if (box.width < 8 || box.height < 8) return false;
          return box.top < innerHeight && box.bottom > 0 && box.left < innerWidth && box.right > 0;
        }""",
        selector,
    )


def _wait(page, js, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        if page.evaluate("() => " + js):
            return
        page.wait_for_timeout(200)
    raise TimeoutError(js)


def _extruders(data: bytes) -> list[int]:
    xml = zipfile.ZipFile(io.BytesIO(data)).read("Metadata/model_settings.config").decode()
    return [int(v) for v in re.findall(r'key="extruder" value="(\d+)"', xml)]


@pytest.fixture(scope="module")
def base():
    while True:
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        if port not in (8765, 8791):
            break
    folder = tempfile.mkdtemp(prefix="zeim-part3mf-")
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


def test_export_download_carries_both_slots_at_phone_and_desktop(base):
    folder = tempfile.mkdtemp(prefix="zeim-part3mf-file-")
    path = os.path.join(folder, "apart.3mf")
    with open(path, "wb") as fh:
        fh.write(_apart())
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
        _wait(page, "document.querySelector('#editExport')")
        for width, height in ((1280, 900), (390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(300)
            if page.locator("#bedPin").is_visible():
                page.locator("#bedPin").click()
                page.wait_for_timeout(200)
            page.evaluate("() => document.querySelector('#bedParts')?.scrollIntoView({block:'nearest', inline:'center'})")
            until = time.time() + 8
            while time.time() < until and not _on_screen(page, "#bedParts"):
                time.sleep(0.1)
            assert _on_screen(page, "#bedParts"), f"{width}x{height}: Parts is not on screen"
            page.locator("#bedParts").click()
            page.wait_for_timeout(200)
            buttons = page.locator("#bedPartsList [data-part]")
            # Selecting a part toggles. Leave only the part being assigned selected.
            for index, slot in ((0, "1"), (1, "2")):
                pressed = buttons.nth(index).get_attribute("aria-pressed") == "true"
                if not pressed:
                    buttons.nth(index).click()
                other = 1 - index
                if buttons.nth(other).get_attribute("aria-pressed") == "true":
                    buttons.nth(other).click()
                page.locator(f"#bedSlotPick button[data-slot='{slot}']").click()
                _wait(page, f"document.querySelectorAll('#bedPartsList [data-part] small')[{index}].textContent.includes('Slot {slot}')")
            page.locator("#partsClose").click()
            page.wait_for_timeout(200)
            # The bed hides the old result bar. Done → Save to this device is the download on screen.
            done = page.locator("#viewEdit [data-ws-act=done]")
            done.scroll_into_view_if_needed()
            done.click()
            page.wait_for_selector("#fdmDone", state="visible", timeout=10000)
            page.locator("[data-fdm-done=device]").click()
            page.wait_for_selector("#ssSave", timeout=15000)
            href = page.locator("#ssSave").get_attribute("href")
            assert href and href.endswith("model.3mf"), href
            page.locator("#ssSave").click()
            _wait(page, "document.querySelector('#ssStatus') && document.querySelector('#ssStatus').textContent.includes('Saved')", timeout=30)
            # The click saves this URL. Read it back through the same session: Chrome's
            # disk cache can leave the click's network body empty in Playwright.
            data = page.request.get(base + href).body()
            xml = zipfile.ZipFile(io.BytesIO(data)).read("3D/3dmodel.model").decode()
            assert "Left" in xml and "Right" in xml
            got = _extruders(data)
            assert 1 in got and 2 in got, got
            page.evaluate("() => { document.getElementById('dlgSendSheet')?.close(); document.getElementById('fdmDone')?.close(); }")
        assert errors == [], errors
        browser.close()
