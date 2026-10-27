"""Recent builds show on My Studio only. Lithophane and the other tool tabs do not get that block.

Studio and Lithophane share #viewCreate. The block used to ride along onto #lithophane.
"""
import os, socket, subprocess, sys, tempfile, time
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None


def _browser_ready():
    if sync_playwright is None:
        return False
    if os.path.exists("/usr/bin/google-chrome") or os.path.exists("/usr/bin/google-chrome-stable"):
        return True
    try:
        with sync_playwright() as p:
            return os.path.exists(p.chromium.executable_path)
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _browser_ready(), reason="needs Playwright and Chrome or Chromium")

READY = """() => window.__zeimStarted === true
  && (document.querySelector('#histNote')?.textContent || '').includes('Tap the star')"""

# Bottom-nav tools that must not show the Studio pickup block. account is Me, which only links to Studio.
OTHER = {
    "showcase": "#viewShowcase",
    "slicer": "#viewEdit",
    "torchc0": "#viewTorch",
    "cad": "#viewCad",
    "smartfix": "#viewFix",
    "learn": "#viewLearn",
    "account": "#viewAccount",
}


def _launch(p):
    exe = getattr(p.chromium, "executable_path", "") or ""
    if exe and os.path.exists(exe):
        return p.chromium.launch()
    return p.chromium.launch(channel="chrome")


@pytest.fixture(scope="module")
def base():
    while True:
        s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        if port not in (8765, 8791):
            break
    d = tempfile.mkdtemp(prefix="zeim-pickup-")
    env = {**os.environ, "PORT": str(port), "HOST": "127.0.0.1", "PHOTO3D_DATA": d + "/d",
           "PHOTO3D_OUT": d + "/o", "PHOTO3D_MODE": "local", "PHOTO3D_AGE_GATE": "0"}
    logf = open(d + "/server.log", "w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-m", "app.serve"], cwd=ROOT, env=env,
                            stdout=logf, stderr=subprocess.STDOUT)
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


def _ready(pg, base, hash_):
    pg.goto(base + "/" + hash_, wait_until="domcontentloaded")
    pg.wait_for_function(READY, timeout=25000)


def _wait_route(pg, hash_, view, main, pickup_hidden):
    """Hash updates before the hashchange handler paints the view. Wait for both."""
    pg.wait_for_function(
        """({hash, view, main, pickupHidden}) => location.hash === hash
            && document.body.dataset.view === view
            && !document.querySelector(main).hidden
            && document.querySelector('#recentBuilds').hidden === pickupHidden""",
        arg={"hash": hash_, "view": view, "main": main, "pickupHidden": pickup_hidden},
        timeout=10000)


def _pickup(pg):
    recent = pg.locator("#recentBuilds")
    return {
        "hidden": recent.evaluate("el => el.hidden"),
        "section": recent.is_visible(),
        "heading": pg.locator("#recentBuilds h2").is_visible(),
        "list": pg.locator("#histList").is_visible(),
        "text": recent.inner_text() if recent.is_visible() else "",
    }


def _assert_off(pg, where):
    got = _pickup(pg)
    assert got["hidden"] is True, (where, got)
    assert got["section"] is False and got["heading"] is False and got["list"] is False, (where, got)


def _assert_on(pg, where):
    got = _pickup(pg)
    assert got["hidden"] is False, (where, got)
    assert got["section"] and got["heading"] and got["list"], (where, got)
    assert "Pick up where you left off" in got["text"], (where, got["text"])
    assert "Tap the star" in got["text"], (where, got["text"])
    assert pg.locator("#histList li").count() >= 1, where


@pytest.mark.parametrize("w", [390, 1280])
def test_pickup_is_on_studio_and_absent_from_lithophane_and_other_tools(base, w):
    with sync_playwright() as p:
        b = _launch(p)
        pg = b.new_page(viewport={"width": w, "height": 844})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))

        _ready(pg, base, "#lithophane")
        assert pg.locator("#viewCreate").is_visible()
        assert pg.locator("#modeCards").is_visible()
        assert pg.locator("#lithoStudioNote").is_visible()
        assert not pg.locator("#studioFromMe").is_visible()
        assert pg.locator("#mainNav button[data-view=lithophane]").get_attribute("aria-current") == "page"
        _assert_off(pg, f"{w} direct #lithophane")

        for view, main in OTHER.items():
            btn = pg.locator(f"#mainNav button[data-view={view}]")
            # Learn is display:none under 420px. The hash still opens that section.
            if btn.is_visible():
                btn.click()
            else:
                pg.evaluate("(view) => { location.hash = view }", view)
            _wait_route(pg, "#" + view, view, main, True)
            assert pg.locator(main).is_visible(), (w, view)
            _assert_off(pg, f"{w} #{view}")
            if view == "account":
                assert pg.locator("#meStudio").is_visible()
                assert pg.locator("#btnMyStudio").is_visible()
                assert "Open Studio" in pg.locator("#btnMyStudio").inner_text()

        pg.locator("#btnMyStudio").click()
        _wait_route(pg, "#studio", "lithophane", "#viewCreate", False)
        assert pg.locator("#viewCreate").is_visible()
        assert pg.locator("#studioFromMe").is_visible()
        assert not pg.locator("#lithoStudioNote").is_visible()
        assert pg.locator("#mainNav button[data-view=account]").get_attribute("aria-current") == "page"
        _assert_on(pg, f"{w} Me → Open Studio")

        pg.locator("#mainNav button[data-view=lithophane]").click()
        _wait_route(pg, "#lithophane", "lithophane", "#viewCreate", True)
        assert pg.locator("#modeCards").is_visible()
        _assert_off(pg, f"{w} back to Lithophane")

        _ready(pg, base, "#studio")
        _assert_on(pg, f"{w} direct #studio")
        _ready(pg, base, "#create")
        _assert_on(pg, f"{w} #create alias")
        assert pg.locator("#mainNav button[data-view=account]").get_attribute("aria-current") == "page"
        _ready(pg, base, "#lithophane")
        _assert_off(pg, f"{w} reload #lithophane")

        assert not errs, errs
        b.close()
