"""TorchC0 (ZEIM's resin program): settings, orient, supports, hollow + drain, estimates, API and UI wiring."""
import io
import zipfile
from pathlib import Path

import pytest
import trimesh

from tests import b1  # noqa: F401  (isolated PHOTO3D_OUT / DATA before the app is imported)
from tests.b1 import ADULT, client

from app.core import resin

ROOT = Path(__file__).resolve().parent.parent


def _stl(m):
    return m.export(file_type="stl")


@pytest.fixture
def c():
    return client(ADULT)


def test_settings_presets_and_limits():
    s = resin.settings()
    assert s["preset"] == "standard" and s["layer_mm"] == 0.05 and s["hollow"] and s["supports"] and s["drain_mm"] > 0
    assert resin.settings({"preset": "detail"})["layer_mm"] == 0.03
    assert resin.settings({"layer_mm": "0.04", "hollow": "false"})["layer_mm"] == 0.04
    for bad in ({"preset": "x"}, {"layer_mm": 1}, {"exposure_s": "abc"}, {"wall_mm": 0.5}, {"tilt_deg": 90}):
        with pytest.raises(resin.ResinError):
            resin.settings(bad)


def test_orient_tilts_and_sits_on_plate():
    m = trimesh.creation.box(extents=[20, 20, 5])
    o = resin.orient(m, 30)
    assert abs(o.bounds[0][2]) < 1e-6 and o.extents[2] > 10


def test_supports_reach_raft_and_skip_inside():
    m = resin.orient(trimesh.creation.box(extents=[20, 20, 5]), 30)
    out, rep = resin.build_supports(m, 4.0, 5.0)
    assert rep["supports"] > 3 and out.bounds[0][2] == pytest.approx(0, abs=1e-6)
    assert out.bounds[1][2] > m.bounds[1][2] + 5


def test_estimate_math():
    s = resin.settings({"layer_mm": 0.05, "bottom_layers": 5, "exposure_s": 2, "bottom_exposure_s": 30, "lift_mm": 6, "lift_speed_mm_min": 60})
    e = resin.estimate(10.0, 5000, s)
    assert e["layers"] == 200 and e["resin_ml"] == 5.0
    assert e["print_seconds"] == round(5 * 30 + 195 * 2 + 200 * (12 + 0.5))


def test_prepare_hollows_with_drain_and_reports():
    m = trimesh.creation.icosphere(subdivisions=3, radius=15)
    out, rep = resin.prepare(m, resin.settings(), bed_mm=[218.88, 122.88, 220])
    assert rep["program"] == "TorchC0" and rep["fits"] and rep["hollow"]["volume_saved_pct"] > 30
    assert rep["support"]["supports"] > 0 and rep["estimate"]["layers"] > 0 and rep["safety"]
    assert rep["estimate"]["resin_ml"] < m.volume / 1000


def test_prepare_too_big_is_flagged():
    _, rep = resin.prepare(trimesh.creation.box(extents=[300, 20, 20]), resin.settings({"hollow": "false", "supports": "false", "tilt_deg": 0}), bed_mm=[200, 120, 200])
    assert rep["fits"] is False and any("Too big" in n for n in rep["notes"])


def test_api_catalog_and_prepare_upload(c):
    cat = c.get("/api/resin/catalog").json()
    assert cat["program"] == "TorchC0" and cat["printers"] and all(p["technology"] == "Resin" for p in cat["printers"])
    assert any(p["id"] == "elegoo_saturn4_ultra" for p in cat["printers"]) and {p["id"] for p in cat["presets"]} == set(resin.PRESETS)
    m = trimesh.creation.box(extents=[20, 15, 10])
    r = c.post("/api/resin/prepare", data={"printer_id": "elegoo_saturn4_ultra", "hollow": "false"},
               files={"file": ("cube.stl", _stl(m), "model/stl")})
    assert r.status_code == 200, r.text
    j = r.json()
    stl = c.get(j["downloads"]["stl"]); assert stl.status_code == 200 and len(stl.content) > 84
    tmf = c.get(j["downloads"]["3mf"]); assert tmf.status_code == 200 and zipfile.is_zipfile(io.BytesIO(tmf.content))
    assert client(ADULT).get(j["downloads"]["stl"]).status_code in (200, 404)   # same-user client may share sid; never a 500


def test_api_rejects_filament_printer_and_bad_input(c):
    m = _stl(trimesh.creation.box(extents=[10, 10, 10]))
    r = c.post("/api/resin/prepare", data={"printer_id": "creality_k1"}, files={"file": ("a.stl", m, "model/stl")})
    assert r.status_code == 400 and "TorchC0" in r.json()["detail"]
    assert c.post("/api/resin/prepare", data={"layer_mm": "5"}, files={"file": ("a.stl", m, "model/stl")}).status_code == 400
    assert c.post("/api/resin/prepare", data={}).status_code == 400
    assert c.get("/api/resin/" + "0" * 32 + "/torchc0.stl").status_code == 404


def test_ui_uses_torchc0_name_and_no_tester_handles():
    js = (ROOT / "static" / "torchc0.js").read_text()
    assert "TorchC0" in js and "/api/resin/prepare" in js and 'id="rzGo"' in js
    for f in ("printer.js", "index.html", "app.js", "torchc0.js", "community.js"):
        assert "cc0hort" not in (ROOT / "static" / f).read_text().lower()


def test_fdm_slicer_and_torchc0_are_separate_main_tabs():
    import re
    html = (ROOT / "static" / "index.html").read_text()
    nav = html[html.index('id="mainNav"'):html.index("</nav>")]
    tabs = dict(re.findall(r'data-view="([a-z0-9]+)".*?<span>([^<]+)</span>', nav))
    assert tabs["slicer"] == "FDM Slicer" and tabs["torchc0"] == "TorchC0"
    assert 'id="viewTorch"' in html and 'id="viewEdit"' in html and "/static/torchc0.js" in html
    torch = html[html.index('id="viewTorch"'):]
    torch = torch[:torch.index("</main>")]
    assert "<h1>TorchC0</h1>" in torch
    com = (ROOT / "static" / "community.js").read_text()
    assert 'torchc0: "#viewTorch"' in com and 'slicer: "#viewEdit"' in com     # old #slicer / #edit URLs still route to the FDM Slicer
    assert 'edit: "slicer"' in com and 'resin: "torchc0"' in com
    # no FDM options in TorchC0, no resin options in the FDM Slicer panel
    tjs = (ROOT / "static" / "torchc0.js").read_text()
    for fdm in ("nozzle_options", "spNozT", "G-code", "filament_grams", "/api/slice"):
        assert fdm not in tjs
    pjs = (ROOT / "static" / "printer.js").read_text()
    for rz in ("rzGo", "/api/resin", "exposure_s", "bottom_exposure"):
        assert rz not in pjs
    assert 'href="#torchc0"' in pjs


def test_torchc0_panel_inputs_are_not_hidden_by_radio_card_css():
    css = (ROOT / "static" / "style.css").read_text()
    assert "label.card input,.seg input{position:absolute" in css and "\n.card input," not in css
    assert 'class="card" id="torchPanel"' not in (ROOT / "static" / "index.html").read_text()


def test_torchc0_in_a_real_browser():
    from test_b4_ui import _run
    out = _run("ui_torchc0.py")
    assert "PASS webkit" in out, out


def test_resin_cost_estimate_per_litre_and_kg():
    e = resin.estimate(10.0, 100000, resin.settings({"price": 40, "price_unit": "l"}))   # 100 ml at 40/l
    assert e["cost"] == 4.0 and "40 per litre" in e["cost_note"]
    k = resin.estimate(10.0, 100000, resin.settings({"price": 40, "price_unit": "kg"}))  # 110 g at 40/kg
    assert k["cost"] == 4.4
    assert resin.estimate(10.0, 100000, resin.settings())["cost"] == round(0.1 * resin.DEFAULT_PRICE, 2)
    with pytest.raises(resin.ResinError):
        resin.settings({"price_unit": "gal"})


def test_api_reports_cost(c):
    r = c.post("/api/resin/prepare", data={"hollow": "false", "supports": "false", "price": "50"},
               files={"file": ("cube.stl", _stl(trimesh.creation.box(extents=[10, 10, 10])), "model/stl")})
    assert r.status_code == 200 and r.json()["estimate"]["cost"] == 0.05
    assert c.get("/api/resin/catalog").json()["default_price"] == resin.DEFAULT_PRICE
