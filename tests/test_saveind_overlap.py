"""The floating "Unsaved changes" pill must not cover a control.

Checked at 360x780, 390x844, 768x1024 and 1280x900 on TorchC0 (before Prepare,
while the resin panel is in the page, and after Prepare on each docked side),
the FDM Slicer, and CAD. Real Chromium. Skipped when Playwright's browser is
not installed. Does not touch port 8765.
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
    with sync_playwright() as _p:
        HAS = os.path.exists(_p.chromium.executable_path)
except Exception:
    HAS = False
pytestmark = pytest.mark.skipif(not HAS, reason="needs playwright Chromium")

VIEWPORTS = [(360, 780), (390, 844), (768, 1024), (1280, 900)]

# Same set worksave.js uses when it slides the pill off a control.
HITS = r"""
() => {
  const pill = document.getElementById("saveInd");
  if (!pill) return {ok: true, hidden: true, hits: []};
  const cs = getComputedStyle(pill);
  const pr = pill.getBoundingClientRect();
  if (cs.display === "none" || cs.visibility === "hidden" || pr.width < 2 || pr.height < 2) {
    return {ok: true, hidden: true, hits: []};
  }
  function visible(el, r) {
    let node = el.parentElement;
    while (node && node !== document.body) {
      const cs = getComputedStyle(node);
      if (/auto|scroll|hidden|clip/.test(cs.overflow + cs.overflowX + cs.overflowY)) {
        const c = node.getBoundingClientRect();
        const left = Math.max(r.left, c.left), top = Math.max(r.top, c.top);
        const right = Math.min(r.right, c.right), bottom = Math.min(r.bottom, c.bottom);
        if (right - left < 1 || bottom - top < 1) return null;
        r = {left, top, right, bottom};
      }
      node = node.parentElement;
    }
    if (r.bottom <= 0 || r.top >= innerHeight || r.right <= 0 || r.left >= innerWidth) return null;
    return r;
  }
  const hits = [];
  document.querySelectorAll("a,button,input,select,textarea,summary,label,[role='button'],[role='tab']").forEach((el) => {
    if (el === pill || pill.contains(el)) return;
    const s = getComputedStyle(el);
    if (s.display === "none" || s.visibility === "hidden" || s.pointerEvents === "none") return;
    let r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return;
    if (el.tagName === "INPUT" && (el.type === "hidden" || el.type === "file") && (r.width < 8 || r.height < 8 || s.opacity === "0")) return;
    r = visible(el, r);
    if (!r) return;
    if (pr.left < r.right - 0.5 && pr.right > r.left + 0.5 && pr.top < r.bottom - 0.5 && pr.bottom > r.top + 0.5) {
      hits.push((el.id || el.getAttribute("aria-label") || el.tagName) + " " + (el.innerText || "").replace(/\s+/g, " ").slice(0, 40));
    }
  });
  return {ok: hits.length === 0, hidden: false, hits: hits.slice(0, 6), label: pill.textContent};
}
"""


def _server():
    while True:
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        if port not in (8765, 8791):
            break
    folder = tempfile.mkdtemp(prefix="zeim-saveind-")
    env = {**os.environ, "PORT": str(port), "HOST": "127.0.0.1", "PHOTO3D_DATA": folder + "/d", "PHOTO3D_OUT": folder + "/o", "PHOTO3D_MODE": "local"}
    proc = subprocess.Popen([sys.executable, "-m", "app.serve"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(160):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.3).close()
            break
        except OSError:
            time.sleep(0.25)
    return proc, f"http://127.0.0.1:{port}", folder


def _stl(folder):
    import trimesh
    path = os.path.join(folder, "cube.stl")
    trimesh.creation.box((20, 15, 10)).export(path)
    return path


def _dirty(page, key):
    page.wait_for_selector("#saveInd", state="attached")
    page.evaluate(
        """(k) => { window.zeimSave._markDirty(k); window.zeimSave.setPrefs({mode: "auto", every: 5}); }""",
        key,
    )
    page.wait_for_function("() => document.getElementById('saveInd').textContent.includes('Unsaved')")


def _settle(page):
    page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")


def _assert_clear(page, where):
    _settle(page)
    got = page.evaluate(HITS)
    assert got["ok"], f"{where}: pill covers {got.get('hits')}"


def _sweep(page, where):
    height = page.evaluate("() => document.documentElement.scrollHeight")
    y = 0
    while y <= height:
        page.evaluate("(y) => scrollTo(0, y)", y)
        _assert_clear(page, f"{where} scroll {y}")
        y += 160


def test_unsaved_pill_does_not_cover_a_control():
    proc, base, folder = _server()
    try:
        stl = _stl(folder)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for width, height in VIEWPORTS:
                page = browser.new_page(viewport={"width": width, "height": height})
                _torch(page, base, stl, width)
                page.close()
                page = browser.new_page(viewport={"width": width, "height": height})
                _fdm(page, base, stl, width)
                page.close()
                page = browser.new_page(viewport={"width": width, "height": height})
                _cad(page, base, width)
                page.close()
            browser.close()
    finally:
        proc.terminate()
        proc.wait(20)


def _torch(page, base, stl, width):
    page.goto(base + "/#torchc0")
    page.wait_for_selector("#rzPrinter", state="attached", timeout=20000)
    page.wait_for_function("() => document.querySelectorAll('#rzPrinter option').length > 2")
    page.select_option("#rzPrinter", label="ELEGOO Jupiter")
    _dirty(page, "torchc0")
    page.set_input_files("#rzFile", stl)
    page.wait_for_function("() => (document.querySelector('#rzFileStatus') || {}).textContent.includes('loaded')", timeout=30000)
    _assert_clear(page, f"torch {width} after load")
    _sweep(page, f"torch {width} before prepare")
    # The panel is still in the page here (not a dock). Prepare mounts the workspace.
    page.locator("#rzGo").click()
    page.wait_for_selector("#viewTorch.zws #zws-settings", timeout=120000)
    _assert_clear(page, f"torch {width} after prepare")
    chip = page.locator("#zws-settings .zws-chip")
    if chip.count() and chip.is_visible():
        chip.click()
        _assert_clear(page, f"torch {width} settings open")
    tools = page.locator("#rzTools")
    if tools.count():
        span = page.evaluate("() => { const el = document.getElementById('rzTools'); return el ? el.scrollHeight : 0; }")
        y = 0
        while y <= span:
            page.evaluate("(y) => { const el = document.getElementById('rzTools'); if (el) el.scrollTop = y; }", y)
            _assert_clear(page, f"torch {width} tools scroll {y}")
            y += 120
    grip = page.locator("#zws-settings .zws-grip")
    if grip.count() and grip.is_visible():
        for n in range(4):
            grip.click()
            _assert_clear(page, f"torch {width} dock side {n}")


def _fdm(page, base, stl, width):
    page.goto(base + "/#slicer")
    page.wait_for_selector("#editFile", state="attached", timeout=20000)
    _dirty(page, "slicer")
    page.set_input_files("#editFile", stl)
    page.wait_for_function("() => { const el = document.querySelector('#editResult'); return el && !el.hidden; }", timeout=30000)
    _assert_clear(page, f"fdm {width} model loaded")
    _sweep(page, f"fdm {width}")
    sheet = page.locator("#viewEdit [data-bed-sheet='process']")
    if sheet.count() and sheet.is_visible():
        sheet.click()
        _assert_clear(page, f"fdm {width} process sheet")


def _cad(page, base, width):
    page.goto(base + "/static/cad.html")
    page.wait_for_selector("#cwTitle", timeout=20000)
    _dirty(page, "cad")
    page.evaluate("""() => {
      const show = document.getElementById("cwShowTools");
      if (show && getComputedStyle(show).display !== "none") show.click();
      const shapes = document.querySelector("[data-tool=shapes]");
      if (shapes) shapes.click();
      const cube = document.querySelector("[data-shape=box]");
      if (cube && !cube.disabled) cube.click();
    }""")
    _assert_clear(page, f"cad {width}")
    _sweep(page, f"cad {width}")
