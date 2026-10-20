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


def _node(code):
    js = (ROOT / "static" / "lithlight.js").as_uri()
    return json.loads(subprocess.run(["node", "--input-type=module", "-e", f"import * as L from '{js}';" + code],
                                     capture_output=True, text=True, check=True).stdout)


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_led_effects_hue_breathe_and_steady_maths():
    o = _node("const b = [1, 0.5, 0.25];"
              "console.log(JSON.stringify({h: [0, 1/3, 2/3, 1].map(h => L.hsv(h)), st: L.effectRGB('steady', b, 7, 5),"
              " br: Array.from({length: 200}, (_, i) => L.effectRGB('breathe', b, i * 0.05, 5)),"
              " rb: Array.from({length: 50}, (_, i) => L.effectRGB('rainbow', b, i * 0.2, 5)),"
              " fd: Array.from({length: 300}, (_, i) => L.effectRGB('fade', b, i * 0.05, 5)), E: L.EFFECTS}))")
    assert o["h"][0] == pytest.approx([1, 0, 0]) and o["h"][1] == pytest.approx([0, 1, 0], abs=1e-9)
    assert o["h"][2] == pytest.approx([0, 0, 1], abs=1e-9) and o["h"][3] == pytest.approx([1, 0, 0])
    assert o["st"] == [1, 0.5, 0.25]
    v = [c[0] for c in o["br"]]
    assert min(v) >= 0.15 - 1e-9 and max(v) == pytest.approx(1, abs=0.01)
    assert all(c[1] == pytest.approx(c[0] * 0.5) for c in o["br"])                # breathe keeps the colour, changes brightness
    assert len({tuple(round(x, 2) for x in c) for c in o["rb"]}) > 20               # rainbow keeps moving
    steps = [max(abs(a - b) for a, b in zip(o["fd"][i], o["fd"][i + 1])) for i in range(299)]
    assert max(steps) < 0.1                                                         # fade is smooth (no jumps)
    assert o["E"] == ["steady", "fade", "rainbow", "breathe", "strobe"]


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_strobe_never_exceeds_3_flashes_per_second_and_reduced_motion_defaults_steady():
    o = _node("const n = []; for (const s of [1, 5, 10, 99]) { let f = 0, prev = 0;"
              " for (let i = 0; i < 10000; i++) { const on = L.effectRGB('strobe', [1, 1, 1], i / 1000, s)[0] > 0 ? 1 : 0; if (on && !prev) f++; prev = on; } n.push(f); }"
              "console.log(JSON.stringify({n, hz: [1, 10, 1e9, -5].map(L.strobeHz), max: L.STROBE_MAX_HZ,"
              " d: [L.defaultEffect('rainbow', true), L.defaultEffect('rainbow', true, true), L.defaultEffect('rainbow', false),"
              "     L.defaultEffect('nope', false), L.defaultEffect(undefined, true)]}))")
    assert o["max"] == 3 and max(o["hz"]) <= 3 and min(o["hz"]) > 0
    assert all(f <= 30 for f in o["n"]) and o["n"][0] < o["n"][2]                  # <= 3 Hz over 10 s, speed still matters
    assert o["d"] == ["steady", "rainbow", "rainbow", "steady", "steady"]


def test_effect_selector_speed_warning_and_loop_hygiene():
    html = (ROOT / "static" / "index.html").read_text()
    for v in ("steady", "fade", "rainbow", "breathe", "strobe"):
        assert f'<option value="{v}">' in html
    assert 'for="vLightFx"' in html and 'type="range" id="vLightSpeed"' in html and "Flashing light" in html
    css = (ROOT / "static" / "style.css").read_text()
    assert "#vLightSpeed { min-height: 44px;" in css and ".fxspeed { display: inline-flex; align-items: center; gap: 6px; min-height: 44px;" in css
    app = (ROOT / "static" / "app.js").read_text()
    tick = app[app.index("function fxTick"):app.index("function syncFx")]
    assert "requestAnimationFrame(fxTick)" in tick and "document.hidden" in tick and "!S.lightOn" in tick and "!viewer" in tick
    assert "new THREE" not in tick and "setBacklight" not in tick                   # no material churn per frame
    assert "prefers-reduced-motion: reduce" in app and "lithStrobeWarned" in app and "localStorage.lithFxSpeed" in app
    assert '"visibilitychange", syncFx' in app
    v = (ROOT / "static" / "viewer.js").read_text()
    assert "setTint(rgb)" in v and "color.setRGB(" in v


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_material_colour_multiplies_the_light():
    o = _node("console.log(JSON.stringify({w: L.transmit([1, 0.5, 0.2], L.materialRGB('white')),"
              " r: L.transmit([1, 1, 1], L.materialRGB('red')), c: L.materialRGB('#808000'), bad: L.materialRGB('nope'),"
              " m: L.transmit(L.lightRGB('#ff0000'), L.materialRGB('blue'))}))")
    assert o["w"] == [1, 0.5, 0.2] and o["r"] == [1.0, 0.35, 0.3] and o["bad"] == [1, 1, 1]
    assert o["c"] == pytest.approx([128 / 255, 128 / 255, 0]) and o["m"] == pytest.approx([0.4, 0, 0])


def test_material_picker_stand_solid_and_expert_resin_presets_wired():
    html = (ROOT / "static" / "index.html").read_text()
    assert 'id="vMatColor"' in html and 'for="vMatColor"' in html and 'type="color" id="vMatRGB"' in html and 'id="lithThk"' in html
    app = (ROOT / "static" / "app.js").read_text()
    assert "localStorage.lithMat" in app and "transmit(effectRGB(" in app and "transmit(fxColour(), matColour())" in app
    assert "THK_IX" in app and '$("#lithThk").onchange = fillLithMat' in app
    v = (ROOT / "static" / "viewer.js").read_text()
    assert "SOLID_PART = /^(stand|base|lid|frame|post|rail)/" in v and "SOLID_PART.test(m.userData.name" in v
    assert "mesh.userData.name = b.name" in v
    assert "stand" in __import__("inspect").getsource(__import__("app.core.geometry", fromlist=["x"]).litho_stand_body)
