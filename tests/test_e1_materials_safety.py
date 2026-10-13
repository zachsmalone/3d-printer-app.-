"""E1 Safety / honest materials: ABS, ASA and PC are sourced (Prusa guides) and labelled not K1-tested; picking one shows a
ventilation + enclosure warning the maker must see before slicing (warn, then allow); the filaments.json TPU key typo is fixed."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.b1 import client
from tests.test_print_core import box_bytes, fake_engine, ini_dict  # noqa: F401  (fixture re-used)
from app import printers
from app.services import print_setup as ps, slice_engine as eng

ROOT = Path(__file__).resolve().parent.parent
PRUSA = {"ABS": "https://help.prusa3d.com/article/abs_2058", "ASA": "https://help.prusa3d.com/article/asa_1809",
         "PC": "https://help.prusa3d.com/article/polycarbonate-pc_165812"}


# ---- sourced data ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("m,noz,bed", [("ABS", 255, 100), ("ASA", 260, 110), ("PC", 275, 115)])
def test_abs_asa_pc_are_sourced_from_prusa_and_say_not_k1_tested(m, noz, bed):
    prof = printers.load_material(m)
    s = prof["settings"]
    assert s["nozzle_temperature_c"]["value"] == noz and s["bed_temperature_c"]["value"] == bed
    for entry in s.values():
        assert entry["sources"] == [PRUSA[m]] and "not K1-tested" in entry["note"]
    assert any("Not tested by ZEIM on a Creality K1" in n for n in prof["notes"])


def test_filaments_json_uses_nozzle_temp_c_everywhere_no_typo():
    raw = (ROOT / "data/materials/filaments.json").read_text()
    assert "nozel" not in raw
    fil = json.loads(raw)["filaments"]
    assert all(isinstance(f.get("nozzle_temp_c"), list) and len(f["nozzle_temp_c"]) == 2 for f in fil)
    assert ps.filament_info("TPU")["nozzle_temp_c"] == [210, 235]          # the reader uses the fixed key


# ---- warning trigger ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("m", ["ABS", "ASA", "PC"])
def test_fume_materials_carry_a_ventilation_and_enclosure_warning(m):
    w = ps.material_safety(m)
    assert w and w["code"] == "ventilation_check" and w["material"] == m
    text = (w["title"] + " " + w["message"]).lower()
    assert "fresh air" in text and "enclosure" in text and "well-ventilated" in text and "not breathe" in text
    assert "not test-printed" in w["tested"] and "K1" in w["tested"]
    assert ps.settings_for("creality_k1", 0.4, {"material": m})["material_warning"] == w


@pytest.mark.parametrize("m", ["PLA", "PETG", "TPU"])
def test_everyday_materials_have_no_fume_warning(m):
    assert ps.material_safety(m) is None and ps.settings_for(None, None, {"material": m})["material_warning"] is None


def test_any_filament_marked_significant_fumes_is_warned(monkeypatch):
    monkeypatch.setattr(ps, "filament_info", lambda m: {"name": "Mystery", "fumes": "Significant; ventilate.", "enclosure": "required"})
    assert ps.material_safety("PLA")["title"].startswith("Mystery")


def test_catalog_sends_the_warning_to_the_ui():
    mats = client().get("/api/printers/catalog").json()["materials"]
    assert set(mats) == {"PLA", "PETG", "TPU", "ABS", "ASA", "PC"}
    assert mats["ABS"]["warning"]["code"] == "ventilation_check" and mats["PLA"]["warning"] is None


def test_reference_temps_above_the_printer_are_capped_and_explained():
    s = ps.settings_for("creality_k1", 0.4, {"material": "PC"})                 # K1: bed max 100 C (catalog), PC reference 115 C
    assert s["bed_temp"] == 100 and s["first_layer_bed_temp"] == 100 and s["nozzle_temp"] == 275
    assert any("115 °C" in n and "100 °C" in n for n in s["temp_notes"])
    assert ps.settings_for("creality_k1", 0.4, {"material": "ABS"})["temp_notes"] == []
    with pytest.raises(ps.SetupError):                                        # an explicit value above the max is still refused
        ps.settings_for("creality_k1", 0.4, {"material": "PC", "bed_temp": "115"})


# ---- API: warn, then allow ------------------------------------------------------------------------------------------
def test_slice_api_asks_first_for_abs_then_slices_after_ventilation_ok(fake_engine):
    c = client()
    r = c.post("/api/slice", files={"file": ("m.stl", box_bytes(10, 10, 10))}, data={"printer_id": "creality_k1", "material": "ABS"})
    assert r.status_code == 409 and not fake_engine
    d = r.json()["detail"]
    assert d["code"] == "ventilation_check" and "enclosure" in d["message"] and d["warning"]["material"] == "ABS"
    r = c.post("/api/slice", files={"file": ("m.stl", box_bytes(10, 10, 10))},
               data={"printer_id": "creality_k1", "material": "ABS", "ventilation_ok": "true"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["material_warning"]["material"] == "ABS" and ini_dict(fake_engine[-1]["ini"])["filament_type"] == "ABS"
    assert ini_dict(fake_engine[-1]["ini"])["temperature"] == "255"


def test_slice_api_pla_needs_no_ack(fake_engine):
    r = client().post("/api/slice", files={"file": ("m.stl", box_bytes(10, 10, 10))}, data={"material": "PLA"})
    assert r.status_code == 200 and r.json()["material_warning"] is None


def test_print_panel_js_shows_and_asks_before_slicing():
    js = (ROOT / "static/printer.js").read_text()
    for s in ("spMatWarn", "matWarnHTML", "ventilation_check", "ventilation_ok", "spVentOk", "spVentNo", 'role="alert"'):
        assert s in js, s


def test_print_panel_warning_in_chrome_and_webkit():
    from test_b1_ui import _spawn
    p, u = _spawn("local")
    try:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tests", "ui_fumes.py"), u], cwd=ROOT, capture_output=True, text=True, timeout=500)
        assert r.returncode == 0 and "FAIL" not in r.stdout and "PASS chrome" in r.stdout, r.stdout + r.stderr
        assert "PASS webkit" in r.stdout or "SKIP webkit" in r.stdout
    finally:
        p.terminate(); p.wait(10)
