"""B: printer kind is one setting everywhere (S1, S2), section logic (S4, S8, S9, P1) and photo tips. Real Chromium; skipped without it."""
import os, socket, subprocess, sys, tempfile, time
import pytest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as _p:
        HAS = os.path.exists(_p.chromium.executable_path)
except Exception:
    HAS = False
pytestmark = pytest.mark.skipif(not HAS, reason="needs playwright Chromium")


@pytest.fixture(scope="module")
def base():
    while True:
        s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        if port not in (8765, 8791): break
    d = tempfile.mkdtemp(prefix="zeim-pkb-")
    env = {**os.environ, "PORT": str(port), "HOST": "127.0.0.1", "PHOTO3D_DATA": d + "/d", "PHOTO3D_OUT": d + "/o", "PHOTO3D_MODE": "local"}
    p = subprocess.Popen([sys.executable, "-m", "app.serve"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(160):
        try: socket.create_connection(("127.0.0.1", port), timeout=0.3).close(); break
        except OSError: time.sleep(0.25)
    yield f"http://127.0.0.1:{port}"
    p.terminate(); p.wait(20)



def _page(p, base, w, kind):
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": w, "height": 860})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(base + "/"); pg.wait_for_selector("#kindPick button[aria-pressed=true]"); pg.wait_for_timeout(500)
    pg.click(f"#kindPick [data-kind={kind}]"); pg.wait_for_timeout(600)
    return b, pg, errs


@pytest.mark.parametrize("w", [1280, 390])
def test_resin_kind_drives_lithophane_and_print_dialog(base, w):
    with sync_playwright() as p:
        b, pg, errs = _page(p, base, w, "resin")
        pg.goto(base + "/#lithophane"); pg.wait_for_timeout(500)
        assert pg.input_value("#lithMaterial") == "resin"                                   # S1
        assert "Resin" in pg.inner_text("#lithKindName") and not pg.is_visible("#lithMaterial")
        pg.evaluate("document.querySelector('#dlgPrint').showModal()")
        assert pg.is_visible("#printToTorch")                                                # S2
        for s in ("#slicerBtns", "#btnSlice", "#s_fill", "#printerBlock"): assert not pg.is_visible(s), s
        pg.click("#printToTorch"); pg.wait_for_timeout(400)
        assert pg.evaluate("location.hash") == "#torchc0" and not pg.evaluate("document.querySelector('#dlgPrint').open")
        pg.click("#kindPick [data-kind=fdm]"); pg.wait_for_timeout(600)                     # back to FDM: everything follows
        pg.goto(base + "/#lithophane"); pg.wait_for_timeout(300)
        assert pg.input_value("#lithMaterial") == "filament" and "Filament" in pg.inner_text("#lithKindName")
        pg.evaluate("document.querySelector('#dlgPrint').showModal()")
        assert not pg.is_visible("#printToTorch") and pg.is_visible("#btnSlice")
        assert not errs, errs
        b.close()


def test_slicer_has_no_photo_flow_and_text_opens_cad(base):
    with sync_playwright() as p:
        b, pg, errs = _page(p, base, 1280, "fdm")
        pg.goto(base + "/#slicer"); pg.wait_for_timeout(500)
        assert pg.is_visible("#editPhotoLink") and not pg.is_visible("#editPhotoMode") and not pg.is_visible("#editPhoto")   # S4
        assert pg.get_attribute("#cadOpenText", "href") == "/static/cad.html?tool=text"                                        # S8
        pg.goto(base + "/static/cad.html?tool=text"); pg.wait_for_timeout(2500)
        assert pg.evaluate("!!document.querySelector('#cwTool') && !document.querySelector('#cwTool').hidden"), "text tool panel not open"
        assert not errs, errs
        b.close()


@pytest.mark.parametrize("w", [1280, 390])
def test_torchc0_beginner_is_simple_and_error_clears(base, w):
    with sync_playwright() as p:
        b, pg, errs = _page(p, base, w, "resin")
        pg.goto(base + "/#torchc0"); pg.wait_for_selector("#rzGo")
        assert pg.is_visible("#rzPreset") and pg.is_visible("#rzHollow") and pg.is_visible("#rzSup")   # S9
        assert not pg.is_visible("#rzExp") and not pg.is_visible("#rzLiftS")
        assert pg.is_visible("#rzDrop label.btn")                                                       # styled picker
        pg.click("#rzAdv > summary"); assert pg.is_visible("#rzExp")
        pg.click("#rzGo"); assert pg.is_visible(".rzNeedFile")                                         # P1
        pg.set_input_files("#rzFile", os.path.join(ROOT, "static", "sample_model.stl")); pg.wait_for_timeout(200)
        assert pg.locator(".rzNeedFile").count() == 0
        assert not errs, errs
        b.close()


@pytest.mark.parametrize("w", [1280, 390])
def test_photo_tips_line_and_expander(base, w):
    with sync_playwright() as p:
        b, pg, errs = _page(p, base, w, "fdm")
        for h in ("#create", "#lithophane"):
            pg.goto(base + "/" + h); pg.wait_for_timeout(400)
            t = pg.locator("#viewCreate .phototips:not(#selPanel .phototips)")   # E adds a second tip inside the select-mode panel
            assert t.count() == 1 and t.is_visible()
            txt = t.inner_text()
            assert "clear subject" in txt and "contrast" in txt and "simple background" in txt and "muddy" in txt
            assert not pg.is_visible("#viewCreate .phototips li")                              # tips folded away
        bb = pg.locator("#viewCreate .phototips:not(#selPanel .phototips)").bounding_box(); assert bb["height"] < 130, bb       # one line-ish, never a blocker
        pg.click("#viewCreate .phototips summary"); assert pg.is_visible("#viewCreate .phototips li")
        assert pg.evaluate("typeof window.zeimPhotoTips") == "function"                        # reusable for select mode
        assert not errs, errs
        b.close()
