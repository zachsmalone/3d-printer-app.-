"""Browser check: Exit, Done, and New build outside CAD do not publish."""
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
    if os.path.exists("/usr/bin/google-chrome") or os.path.exists("/usr/bin/google-chrome-stable") or os.path.exists("/usr/local/bin/google-chrome"):
        return True
    try:
        with sync_playwright() as p:
            return os.path.exists(p.chromium.executable_path)
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _browser_ready(), reason="needs Playwright and Chrome or Chromium")

READY = "() => window.__zeimStarted === true && !!document.querySelector('#viewCreate .wsbar')"


def _launch(p):
    exe = getattr(p.chromium, "executable_path", "") or ""
    if exe and os.path.exists(exe):
        return p.chromium.launch()
    for path in ("/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/local/bin/google-chrome"):
        if os.path.exists(path):
            return p.chromium.launch(executable_path=path)
    return p.chromium.launch(channel="chrome")


@pytest.fixture(scope="module")
def base():
    while True:
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        if port not in (8765, 8791):
            break
    d = tempfile.mkdtemp(prefix="zeim-exit-")
    env = {**os.environ, "PORT": str(port), "HOST": "127.0.0.1", "PHOTO3D_DATA": d + "/d",
           "PHOTO3D_OUT": d + "/o", "PHOTO3D_MODE": "local", "PHOTO3D_AGE_GATE": "0"}
    logf = open(d + "/server.log", "w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-m", "app.serve"], cwd=ROOT, env=env, stdout=logf, stderr=subprocess.STDOUT)
    up = False
    for _ in range(160):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.3).close()
            up = True
            break
        except OSError:
            if proc.poll() is not None:
                logf.flush()
                err = open(d + "/server.log", encoding="utf-8", errors="replace").read()[-2000:]
                raise RuntimeError("server exited\n" + err)
            time.sleep(0.25)
    if not up:
        logf.flush()
        err = open(d + "/server.log", encoding="utf-8", errors="replace").read()[-2000:]
        proc.terminate()
        raise RuntimeError("server did not start\n" + err)
    yield f"http://127.0.0.1:{port}"
    proc.terminate()
    try:
        proc.wait(20)
    except subprocess.TimeoutExpired:
        proc.kill()
    logf.close()


def _open(pg, base, hash_):
    pg.goto(base + "/" + hash_, wait_until="domcontentloaded")
    pg.wait_for_function(READY, timeout=25000)
    pg.wait_for_function(
        "() => { const w = document.querySelector('#saveWhere'); return !!w && !/checking/.test(w.textContent || ''); }",
        timeout=15000,
    )


def test_exit_new_build_and_done_do_not_publish(base):
    with sync_playwright() as p:
        browser = _launch(p)
        pg = browser.new_page(viewport={"width": 1280, "height": 800})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        _open(pg, base, "#lithophane")
        pg.evaluate("""() => {
          window.__published = 0;
          window.zeimOpenShowcase = () => { window.__published += 1; };
        }""")
        bar = pg.locator("#viewCreate .wsbar")
        assert bar.locator("[data-ws-act=exit]").inner_text() == "Exit"
        assert bar.locator("[data-ws-act=new-build]").inner_text() == "New build"
        assert bar.locator("[data-ws-act=done]").is_hidden()
        assert bar.locator("[data-ws-act=return-studio]").is_hidden()
        assert pg.locator("#btnPublish").inner_text().find("Send to Showcase") >= 0

        bar.locator("[data-ws-act=new-build]").click()
        pg.wait_for_timeout(200)
        assert pg.evaluate("() => location.hash") == "#lithophane"
        assert "publish" not in pg.evaluate("() => location.search + location.hash")
        assert pg.evaluate("() => window.__published") == 0

        for view, root in (("slicer", "#viewEdit"), ("torchc0", "#viewTorch"), ("ai3d", "#viewAi3d")):
            pg.evaluate("(view) => { location.hash = view }", view)
            pg.wait_for_function(
                """({view, root}) => location.hash === '#' + view && document.querySelector(root + ' .wsbar')""",
                arg={"view": view, "root": root},
                timeout=10000,
            )
            row = pg.locator(root + " .wsbar")
            assert row.locator("[data-ws-act=exit]").is_visible()
            if view == "slicer":
                assert row.locator("[data-ws-act=exit]").inner_text() == "Back"
                assert row.locator("[data-ws-act=done]").is_visible()
                bar = pg.locator("#slicerBar")
                assert bar.is_hidden()
                assert bar.locator("[data-bed-sheet=filament]").text_content() == "Filament"
                assert bar.locator("[data-bed-sheet=process]").text_content() == "Process"
                assert bar.locator("[data-bed-act=import]").count() == 1
                assert pg.locator("#mainNav button[data-view=projects]").count() == 0
            else:
                assert row.locator("[data-ws-act=new-build]").is_visible()
                assert row.locator("[data-ws-act=return-studio]").is_hidden()

        pg.evaluate("""() => {
          sessionStorage.setItem('zeim.back', JSON.stringify({
            label: 'My Studio', hash: 'account', url: '/#account/studio', from: 'mystudio', t: Date.now()
          }));
          location.hash = 'lithophane';
        }""")
        pg.wait_for_function("() => location.hash === '#lithophane' && document.body.dataset.view === 'lithophane'")
        assert pg.locator("#viewCreate .wsbar [data-ws-act=return-studio]").is_visible()
        assert pg.locator("#studioFromMe").is_visible()
        pg.locator("#viewCreate .wsbar [data-ws-act=exit]").click()
        pg.wait_for_function("() => location.hash === '#account' && document.body.dataset.view === 'account'")
        assert "publish" not in pg.url
        assert pg.evaluate("() => window.__published") == 0
        assert pg.locator("#viewCreate").is_hidden()
        assert pg.locator("#viewAccount").is_visible()
        assert pg.locator("#viewProjects").count() == 0
        assert pg.locator("#studioLib").is_visible()
        assert errs == [], errs
        browser.close()
