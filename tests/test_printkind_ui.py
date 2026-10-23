"""FDM / Resin switch (persists, sets defaults, both tabs reachable) + header fits the viewport. Real Chromium; skipped without it."""
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
    d = tempfile.mkdtemp(prefix="zeim-pk-")
    env = {**os.environ, "PORT": str(port), "HOST": "127.0.0.1", "PHOTO3D_DATA": d + "/d", "PHOTO3D_OUT": d + "/o", "PHOTO3D_MODE": "local"}
    p = subprocess.Popen([sys.executable, "-m", "app.serve"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(160):
        try: socket.create_connection(("127.0.0.1", port), timeout=0.3).close(); break
        except OSError: time.sleep(0.25)
    yield f"http://127.0.0.1:{port}"
    p.terminate(); p.wait(20)


FIT = """()=>{const h=document.querySelector('.topbar'),W=innerWidth;
 const bad=[...h.querySelectorAll('*')].filter(e=>{const r=e.getBoundingClientRect();return r.width&&getComputedStyle(e).position!=='absolute'&&(r.right>W+0.5||r.left<-0.5)&&!e.closest('#mainNav')});
 return {sw:h.scrollWidth,cw:h.clientWidth,doc:document.documentElement.scrollWidth,W,bad:bad.map(e=>e.id||e.className),
  theme:document.querySelector('#themeToggle').getBoundingClientRect().right}}"""


@pytest.mark.parametrize("w", [1280, 960, 390, 320])
def test_header_fits(base, w):
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": w, "height": 800})
        pg.goto(base + "/"); pg.wait_for_selector("#kindPick button[aria-pressed=true]"); pg.wait_for_timeout(800)
        r = pg.evaluate(FIT)
        assert r["sw"] <= r["cw"] and r["doc"] <= w and r["theme"] <= w and not r["bad"], r
        for btn in pg.query_selector_all("#kindPick button"):
            bb = btn.bounding_box(); assert bb["height"] >= 44 and bb["width"] >= 44
        if w == 390: pg.screenshot(path=os.path.join(tempfile.gettempdir(), "zeim-printkind-390.png"))
        b.close()


@pytest.mark.parametrize("w", [1280, 390, 320])
def test_switch_persists_and_sets_defaults(base, w):
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": w, "height": 800})
        pg.goto(base + "/"); pg.wait_for_selector("#kindPick button[aria-pressed=true]"); pg.wait_for_timeout(800)
        assert pg.get_attribute("#kindPick [data-kind=fdm]", "aria-pressed") == "true"      # default printer K1 is FDM -> preselected
        assert "kind-primary" in pg.get_attribute("#mainNav [data-view=slicer]", "class")
        pg.click("#kindPick [data-kind=resin]"); pg.wait_for_timeout(800)
        pg.reload(); pg.wait_for_selector("#kindPick [data-kind=resin][aria-pressed=true]"); pg.wait_for_timeout(800)
        assert pg.evaluate("document.body.dataset.printKind") == "resin"
        assert "kind-primary" in pg.get_attribute("#mainNav [data-view=torchc0]", "class")
        assert pg.evaluate("JSON.parse(localStorage.getItem('zeim.printer')).nozzle") is None           # Will-it-print printer follows: resin
        pg.goto(base + "/#print"); pg.wait_for_timeout(600)
        assert pg.evaluate("location.hash") == "#torchc0" and pg.is_visible("#viewTorch")
        assert pg.get_attribute('#viewFix a[data-kind-link]', "href") == "#torchc0"
        for v, sel in (("slicer", "#viewEdit"), ("torchc0", "#viewTorch")):                          # both tabs stay reachable
            pg.click(f"#mainNav [data-view={v}]"); pg.wait_for_timeout(300); assert pg.is_visible(sel)
        pg.click("#mainNav [data-view=slicer]"); pg.wait_for_timeout(300)
        n = pg.query_selector("#viewEdit .kindnote")
        assert n and n.is_visible(); pg.click("#viewEdit .kindnote .x"); assert not pg.query_selector(".kindnote")
        pg.click("#kindPick [data-kind=fdm]"); pg.wait_for_timeout(800); pg.reload(); pg.wait_for_timeout(1200)
        assert pg.get_attribute("#kindPick [data-kind=fdm]", "aria-pressed") == "true"
        assert "kind-primary" in pg.get_attribute("#mainNav [data-view=slicer]", "class")
        b.close()
