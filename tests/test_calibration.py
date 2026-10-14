"""Calibration wizard (Zach 2026-10-13): first layer, temperature tower, flow, retraction for the picked printer +
nozzle + filament. Plain-words steps, what to look for, real PrusaSlicer keys from the Smart Fix map; models fit the
bed; temperature tower bands capped to the printer; ABS/ASA/PC ask once; resin printers get the resin note."""
import os
import shutil

import pytest
import trimesh
from fastapi.testclient import TestClient

from app.main import app
from app.services import calibration as cal
from app.services import print_setup as ps

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
c = TestClient(app)
PRUSA_KEYS = {"z_offset", "first_layer_speed", "bed_temperature", "temperature", "extrusion_multiplier", "retract_length",
              "retract_speed", "avoid_crossing_perimeters"}


def test_plan_for_k1_pla_has_four_plain_tests_with_real_keys():
    r = c.get("/api/calibration/plan", params={"printer_id": "creality_k1", "nozzle": "0.4", "material": "PLA"})
    assert r.status_code == 200
    j = r.json()
    assert [t["id"] for t in j["tests"]] == ["first_layer", "temp_tower", "flow", "retraction"]
    assert j["printer"] == "Creality K1" and j["nozzle"] == 0.4 and not j["resin"]
    assert "estimate" in j["estimate_note"].lower() and "not tested" in j["estimate_note"].lower()
    for t in j["tests"]:
        assert t["steps"] and t["good"] and t["bad"] and all({"see", "means", "do"} <= set(b) for b in t["bad"])
        keys = {s["key"] for s in t["settings"] if s["key"]}
        assert keys and keys <= PRUSA_KEYS, keys
        assert all(s["confirm"] for s in t["settings"] if s["key"])        # never auto-applied
    tt = j["tests"][1]["values"]
    assert tt["bands_c"] == [220, 215, 210, 205, 200, 195]                 # Prusa PLA 210 °C: +10 down to -15
    assert j["tests"][3]["values"]["start_retract_mm"] == 0.8 and j["tests"][3]["values"]["from_profile"]   # K1 profile
    assert j["tests"][2]["values"]["expected_wall_mm"] == pytest.approx(0.8, abs=0.02)


def test_temperature_bands_never_exceed_the_printer():
    p = ps.printer_public("creality_k1")                                   # 300 °C max
    assert max(cal.temp_bands(p, "PC")) <= 300
    tpu = cal.temp_bands(p, "TPU")                                         # sourced range 220-240
    assert tpu[0] == 240 and tpu[-1] >= 215 and all(a - b == 5 for a, b in zip(tpu, tpu[1:]))
    low = dict(p, max_nozzle_c=250)
    assert max(cal.temp_bands(low, "PETG")) == 250


def test_resin_printer_gets_the_resin_note_and_no_models():
    j = c.get("/api/calibration/plan", params={"printer_id": "elegoo_mars4"}).json()
    assert j["resin"] and j["tests"] == [] and "exposure test" in j["message"] and "gloves" in j["safety"] and "IPA" in j["safety"]
    assert c.get("/api/calibration/flow.stl", params={"printer_id": "elegoo_mars4"}).status_code == 400


def test_bad_input_is_a_plain_error():
    assert c.get("/api/calibration/plan", params={"material": "Wood"}).status_code == 400
    assert c.get("/api/calibration/plan", params={"printer_id": "nope"}).status_code == 400
    assert c.get("/api/calibration/plan", params={"nozzle": "abc"}).status_code == 400
    assert c.get("/api/calibration/spaghetti.stl").status_code == 404


@pytest.mark.parametrize("pid", ["creality_k1", "bambu_a1_mini", "prusa_mini_plus", "elegoo_neptune4_max"])
@pytest.mark.parametrize("test", cal.TESTS)
def test_models_are_watertight_and_fit_the_bed(pid, test):
    r = c.get(f"/api/calibration/{test}.stl", params={"printer_id": pid})
    assert r.status_code == 200 and r.headers["content-disposition"].endswith(f'zeim-calibration-{test}.stl"')
    m = trimesh.load(trimesh.util.wrap_as_stream(r.content), file_type="stl")
    x, y, z = ps.bed_of(pid)
    ext = m.extents
    assert ext[0] <= x and ext[1] <= y and ext[2] <= z
    if test != "first_layer":                    # five separate squares: each watertight, not one body
        assert m.is_watertight
    if test == "first_layer":
        assert ext[2] == pytest.approx(0.2) and len(m.split(only_watertight=True)) == 5


def test_temperature_band_insertion(tmp_path):
    g = tmp_path / "t.gcode"
    lines = []
    for i in range(1, 100):
        lines += [";LAYER_CHANGE\n", f";Z:{i * 0.2:.1f}\n", "G1 X1 Y1 E1\n"]
    g.write_text("M104 S215\n" + "".join(lines))
    assert cal.add_temperature_bands(g, [220, 215, 210]) == 3
    out = g.read_text().splitlines()
    at = [out[i - 1] for i, l in enumerate(out) if "ZEIM temperature tower" in l]
    assert at == [";Z:1.2", ";Z:9.2", ";Z:17.2"]


def test_slice_tests_with_the_real_engine():
    from app.services import slice_engine as eng
    if not eng.find_engine():
        pytest.skip("PrusaSlicer not installed")
    for test in cal.TESTS:
        r = c.post(f"/api/calibration/{test}/slice", data={"printer_id": "creality_k1", "nozzle": "0.4", "material": "PLA"})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["print_time_seconds"] and j["filament_grams"]
        g = c.get(j["downloads"]["gcode"]).text
        bands = [l for l in g.splitlines() if "ZEIM temperature tower" in l]
        if test == "temp_tower":
            assert j["temperature_bands_c"] == [220, 215, 210, 205, 200, 195]
            assert [l.split()[1] for l in bands] == ["S220", "S215", "S210", "S205", "S200", "S195"]
        else:
            assert not bands
        assert c.get(j["downloads"]["layers"]).status_code == 200      # layer preview works on calibration slices too


def test_fume_material_asks_once_before_slicing():
    r = c.post("/api/calibration/flow/slice", data={"printer_id": "creality_k1", "material": "ABS"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "ventilation_check"


def test_smart_fix_page_has_the_wizard():
    html = open(os.path.join(ROOT, "static", "index.html"), encoding="utf-8").read()
    js = open(os.path.join(ROOT, "static", "calibrate.js"), encoding="utf-8").read()
    assert 'id="calOpen"' in html and 'id="calBox"' in html and "/static/calibrate.js" in html
    assert "never changes them for you" in js and "esc(" in js


def test_calibration_wizard_in_a_real_browser():
    from test_b4_ui import _run
    out = _run("ui_calibrate.py")
    assert "PASS webkit" in out, out
