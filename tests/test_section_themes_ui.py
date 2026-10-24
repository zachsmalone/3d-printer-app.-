"""Section themes: each section has its own art band and accent, and prefers-reduced-motion turns all theme animation off."""
import os, re, socket, subprocess, sys, tempfile, time
import pytest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(ROOT, "static", "index.html"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "static", "zeim-themes.css"), encoding="utf-8").read()
CAD = open(os.path.join(ROOT, "static", "cad.html"), encoding="utf-8").read()
SECS = {"viewShowcase": "showcase", "viewEdit": "slicer", "viewTorch": "torchc0", "viewCad": "cad", "viewCreate": "lithophane", "viewFix": "smartfix", "viewLearn": "learn", "viewAccount": "account"}
MOTION = {
    "showcase": "zt-petal",
    "torchc0": "zt-ember",
    "slicer": "zt-wave",
    "lithophane": "zt-glow",
    "account": "zt-ink",
    "cad": "zt-mist",
}


def test_every_section_has_its_theme_band():
    assert '/static/zeim-themes.css' in HTML
    for vid, sec in SECS.items():
        m = re.search(r'<main [^>]*id="%s"[^>]*>\s*<div class="zt-band" data-zt="%s"' % (vid, sec), HTML)
        assert m, vid
        assert f"[data-zt={sec}]" in CSS, sec


def test_main_sections_have_subtle_motion_markup():
    for sec, cls in MOTION.items():
        i = HTML.find('data-zt="%s"' % sec)
        assert i >= 0, sec
        assert cls in HTML[i:i + 900], (sec, cls)


def test_theme_assets_small_and_present():
    d = os.path.join(ROOT, "static", "zt"); total = 0
    for sec in ("showcase", "slicer", "torchc0", "cad", "learn", "account"):
        for f in (sec + ".webp", sec + "@2x.webp"):
            total += os.path.getsize(os.path.join(d, f))
    total += os.path.getsize(os.path.join(d, "lithophane-cat.jpg"))
    assert total < 260_000


def test_reduced_motion_rule_disables_theme_animation():
    rm = CSS[CSS.index("@media (prefers-reduced-motion:reduce)"):]
    assert "animation:none!important" in rm
    for cls in (".zt-petal", ".zt-ember", ".zt-wave", ".zt-mist", ".zt-ink", ".zt-glow"):
        assert cls in rm and "display:none" in rm
    for kf in re.findall(r"@keyframes (zt-[a-z]+)\{((?:[^{}]*\{[^{}]*\})*)\}", CSS):   # animations only use transform/opacity
        props = set(re.findall(r"([a-z-]+):", kf[1]))
        assert props <= {"transform", "opacity"}, kf[0]


def test_cad_work_canvas_has_no_theme_band():
    """Ronin mist is for #viewCad home/empty/success landing only — never over the CAD workspace."""
    assert "zt-band" not in CAD and "zeim-themes" not in CAD and "zt-mist" not in CAD
    assert "#viewCad" in CSS or "viewCad" in CSS
    assert "cad.html" in CSS  # documented never-on-canvas guard in the stylesheet header


def test_copy_is_humble_and_adult():
    band = " ".join(re.findall(r'<div class="zt-band".*?</div>\n', HTML, re.S)).lower()
    for w in ("kid", "child", "family", "school", "best", "fastest", "%"):
        assert w not in band


try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as _p:
        HAS = os.path.exists(_p.chromium.executable_path)
except Exception:
    HAS = False


@pytest.mark.skipif(not HAS, reason="needs playwright Chromium")
def test_section_themes_in_browser():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    d = tempfile.mkdtemp(prefix="zeim-ui-")
    env = {**os.environ, "PORT": str(port), "HOST": "127.0.0.1", "PHOTO3D_DATA": d + "/d", "PHOTO3D_OUT": d + "/o", "PHOTO3D_MODE": "local"}
    p = subprocess.Popen([sys.executable, "-m", "app.serve"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(120):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.3).close(); break
            except OSError:
                time.sleep(0.25)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tests", "ui_section_themes.py"), f"http://127.0.0.1:{port}"], cwd=ROOT, capture_output=True, text=True, timeout=400)
        assert r.returncode == 0, r.stdout + r.stderr
    finally:
        p.terminate(); p.wait(20)
