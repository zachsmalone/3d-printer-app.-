"""'Light on' backlit lithophane preview: brightness from wall thickness (Beer-Lambert style), flat and curved shapes."""
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from app.core import litho_light as ll

ROOT = Path(__file__).resolve().parent.parent


def test_brightness_is_exp_minus_kt_thin_bright_thick_dark():
    assert ll.brightness(0) == pytest.approx(1.0)
    assert ll.brightness(1.0, k=0.9) == pytest.approx(np.exp(-0.9))
    t = np.array([0.6, 0.8, 1.6, 3.2])
    b = ll.brightness(t)
    assert np.all(np.diff(b) < 0)                                # thicker -> darker
    assert ll.brightness(-1) == pytest.approx(1.0)               # no negative thickness
    d = ll.display(t)
    assert d[0] == pytest.approx(1.0) and np.all((d >= 0) & (d <= 1))


def _ring(r, z):
    a = np.linspace(0, 2 * np.pi, 36, endpoint=False)
    return np.c_[r * np.cos(a), r * np.sin(a), np.full_like(a, z)]


def test_wall_thickness_flat_cylinder_and_globe():
    flat = np.array([[0, 0, 0], [1, 0, 0.8], [2, 0, 3.2]])
    assert ll.wall_thickness(flat, "rect") == pytest.approx([0, 0.8, 3.2])
    cup = np.vstack([_ring(20, z) for z in (0, 10, 20, 30)] + [_ring(22.5, z) for z in (0, 10, 20, 30)])
    t = ll.wall_thickness(cup, "cup")
    assert t[:144].max() == pytest.approx(0, abs=1e-6) and t[144:] == pytest.approx(2.5, abs=1e-6)
    # globe: sphere radius 25 (outer) / 23 (inner) centred at z=30, with a foot at z=0..5
    rng = np.random.default_rng(0)
    u = rng.normal(size=(400, 3)); u /= np.linalg.norm(u, axis=1)[:, None]; u = u[u[:, 2] > -0.6]
    c = np.array([0, 0, 30.0])
    pts = np.vstack([c + 25 * u, c + 23 * u, [[25, 0, 30], [-25, 0, 30], [0, 25, 30], [0, -25, 30], [0, 0, 55]]])
    tg = ll.wall_thickness(pts, "globe")
    n = len(u)
    assert np.median(tg[:n]) == pytest.approx(2.0, abs=0.05) and np.median(tg[n:2 * n]) == pytest.approx(0, abs=0.05)


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_js_twin_matches_python():
    js = (ROOT / "static" / "lithlight.js").as_uri()
    pts = [0, 0, 0, 1, 0, 0.8, 2, 0, 3.2]
    code = (f"import {{ brightness, wallThickness, K_PER_MM, backlitColors }} from '{js}';"
            f"const t = Array.from(wallThickness(new Float32Array({pts}), 'rect'));"
            f"console.log(JSON.stringify({{k: K_PER_MM, b: [0, 0.8, 3.2].map(x => brightness(x)), t, c: Array.from(backlitColors(new Float32Array({pts}), 'rect', 'white')) }}));")
    out = json.loads(subprocess.run(["node", "--input-type=module", "-e", code], capture_output=True, text=True, check=True).stdout)
    assert out["k"] == ll.K_PER_MM
    assert out["b"] == pytest.approx(list(ll.brightness([0, 0.8, 3.2])), rel=1e-6)
    assert out["t"] == pytest.approx([0, 0.8, 3.2], abs=1e-6)
    assert out["c"][0] == pytest.approx(1.0) and out["c"][-1] < out["c"][3] < out["c"][0]


def test_light_toggle_is_labelled_and_accessible():
    html = (ROOT / "static" / "index.html").read_text()
    assert 'id="vLight"' in html and 'aria-pressed="false"' in html and "Light on" in html
    assert "Preview estimate" in html and 'for="vLightColor"' in html
    for c in ("warm", "cool", "white"):
        assert f'value="{c}"' in html


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_js_curved_shapes_and_light_colours():
    js = (ROOT / "static" / "lithlight.js").as_uri()
    code = (f"import {{ wallThickness, backlitColors, LIGHTS }} from '{js}';"
            "const P = []; for (const r of [20, 22.5]) for (const z of [0, 10, 20, 30]) for (let a = 0; a < 36; a++)"
            " P.push(r * Math.cos(a / 36 * 2 * Math.PI), r * Math.sin(a / 36 * 2 * Math.PI), z);"
            "const pos = new Float32Array(P), t = Array.from(wallThickness(pos, 'cup')), n = Array.from(wallThickness(pos, 'nightlight'));"
            "const c = {}; for (const l of ['warm', 'cool', 'white', 'bogus']) c[l] = Array.from(backlitColors(pos, 'cup', l).slice(0, 3));"
            "console.log(JSON.stringify({t, n, c, L: LIGHTS}));")
    out = json.loads(subprocess.run(["node", "--input-type=module", "-e", code], capture_output=True, text=True, check=True).stdout)
    assert max(out["t"][:144]) == pytest.approx(0, abs=1e-5) and out["t"][144:] == pytest.approx([2.5] * 144, abs=1e-4)
    assert out["n"] == pytest.approx(out["t"], abs=1e-6)
    assert out["c"]["warm"] == pytest.approx(out["L"]["warm"]) and out["c"]["cool"] == pytest.approx(out["L"]["cool"])
    assert out["c"]["bogus"] == pytest.approx([1, 1, 1])                       # unknown colour falls back to white
    assert all(0 <= x <= 1 for v in out["c"].values() for x in v)


def test_viewer_backlight_restores_material_and_keeps_wireframe_in_step():
    v = (ROOT / "static" / "viewer.js").read_text()
    body = v[v.index("setBacklight(on"):v.index("toggleWire()")]
    assert "m.userData.lit" in body and ".dispose()" in body and "this.wire" in body
    tw = v[v.index("toggleWire()"):]
    assert "userData.lit.wireframe" in tw[:300]
    app = (ROOT / "static" / "app.js").read_text()
    assert "S.lightOn = false; syncLight();" in app                            # new build starts with light off
    assert 'S.current?.mode === "lithophane"' in app and "litShapeOf(S.current)" in app


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_js_custom_rgb_and_sunlight():
    js = (ROOT / "static" / "lithlight.js").as_uri()
    pts = [0, 0, 0, 1, 0, 0.8, 2, 0, 3.2]
    code = (f"import {{ lightRGB, backlitColors, LIGHTS }} from '{js}';"
            f"const c = Array.from(backlitColors(new Float32Array({pts}), 'rect', '#ff8000'));"
            "console.log(JSON.stringify({c, red: lightRGB('#FF0000'), bad: lightRGB('#zz'), sun: lightRGB('sunlight'), L: LIGHTS}));")
    out = json.loads(subprocess.run(["node", "--input-type=module", "-e", code], capture_output=True, text=True, check=True).stdout)
    assert out["red"] == [1, 0, 0] and out["bad"] == [1, 1, 1]
    assert out["c"][:3] == pytest.approx([1, 128 / 255, 0], abs=1e-6)          # thinnest glows the bulb colour
    assert out["c"][5] == 0 and out["c"][6] < out["c"][3] < out["c"][0]          # tint kept, thicker darker
    sun = out["sun"]
    assert sun == pytest.approx(list(ll.LIGHTS["sunlight"]))                      # python twin in step
    assert min(sun) > 0.9 and sun[2] > sun[0]                                     # bright, slightly blue-white
    assert all(sun != out["L"][k] for k in ("warm", "cool", "white"))


def test_custom_and_sunlight_ui_is_tap_friendly_and_remembered():
    html = (ROOT / "static" / "index.html").read_text()
    assert 'value="sunlight"' in html and 'value="custom"' in html
    assert 'type="color" id="vLightRGB"' in html and 'for="vLightRGB"' in html
    css = (ROOT / "static" / "style.css").read_text()
    assert "#vLightRGB { min-width: 44px; min-height: 44px;" in css and "flex-wrap: wrap" in css
    app = (ROOT / "static" / "app.js").read_text()
    assert "localStorage.lithLight" in app and "localStorage.lithLightRGB" in app and '"#vLightRGB").oninput' in app
