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
