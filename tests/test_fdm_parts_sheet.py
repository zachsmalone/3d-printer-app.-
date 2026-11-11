"""Parts and Detect parts are on the FDM bed, not only in the hidden side panel.

The check is a real browser at phone and desktop size. It fails when the control
is in the DOM but display:none, or when its box is outside the viewport.
Skipped when Playwright or Chrome is missing.
"""
import os
import socket
import subprocess
import sys
import tempfile
import time

import pytest

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


def _wait(page, js, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        if page.evaluate("() => " + js):
            return
        page.wait_for_timeout(200)
    raise TimeoutError(js)


def _on_screen(page, selector):
    """True only when the element is painted inside the viewport, not merely present."""
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


@pytest.fixture(scope="module")
def base():
    while True:
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        if port not in (8765, 8791):
            break
    folder = tempfile.mkdtemp(prefix="zeim-parts-ui-")
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


def test_parts_sheet_is_on_screen_at_phone_and_desktop(base):
    with sync_playwright() as p:
        browser = _launch(p)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.goto(base + "/#slicer", wait_until="domcontentloaded")
        page.wait_for_selector("#editSample", state="visible", timeout=20000)
        page.click("#editSample")
        _wait(page, "document.querySelector('#viewEdit').classList.contains('has-model') && !document.querySelector('#editResult').hidden && document.querySelector('#bedPartsList li')")
        # The old home is the side panel, which the bed hides. The button must not live only there.
        assert page.evaluate("() => !document.querySelector('#editDetectParts')?.closest('#editSide')")
        assert page.evaluate("() => getComputedStyle(document.querySelector('#editSide')).display === 'none'")
        for width, height in ((1280, 900), (390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(300)
            page.evaluate("() => document.querySelector('#bedParts')?.scrollIntoView({block:'nearest', inline:'center'})")
            seen = False
            until = time.time() + 8
            while time.time() < until:
                if _on_screen(page, "#bedParts"):
                    seen = True
                    break
                time.sleep(0.1)
            assert seen, f"{width}x{height}: Parts on the bar is not on screen"
            assert not _on_screen(page, "#editDetectParts"), f"{width}x{height}: Detect parts is showing before the sheet opens"
            page.locator("#bedParts").click()
            page.wait_for_timeout(200)
            assert _on_screen(page, "#editDetectParts"), f"{width}x{height}: Detect parts is not on screen"
            assert _on_screen(page, "#bedPartsList li"), f"{width}x{height}: part name is not on screen"
            assert _on_screen(page, "#bedPartsList .bed-swatch"), f"{width}x{height}: colour swatch is not on screen"
            assert page.locator("#editDetectParts").inner_text() == "Detect parts"
            page.locator("#partsClose").click()
            page.locator("#bedPin").click()
            page.wait_for_timeout(100)
        assert errors == [], errors
        browser.close()
