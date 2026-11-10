"""Support filament is a PrusaSlicer extruder only when the loaded ini has that extruder.

PrusaSlicer 2.9.2 counts extruders from nozzle_diameter and filament_diameter
(PresetBundle uses the shorter of the two). ZEIM's catalog profiles write one
value for each, so a second support extruder is not set.
"""
import json
import re
from dataclasses import replace
from pathlib import Path

import trimesh
from fastapi.testclient import TestClient

from app.main import app
from app.services import print_setup as ps
from app.services import slice_engine as eng
from app.services import support_extruder as sx
from app.services.slice_engine import PrinterProfile

ROOT = Path(__file__).resolve().parents[1]
TWO = "nozzle_diameter = 0.4,0.4\nfilament_diameter = 1.75,1.75\nsupport_material = 1\n"


def _profile(ini: str) -> PrinterProfile:
    return PrinterProfile("lab", "Lab", 220, 220, 250, 0.4, "PLA", ini)


def _box_stl() -> bytes:
    return trimesh.creation.box(extents=(12, 12, 6)).export(file_type="stl")


def test_single_nozzle_is_one_extruder():
    ini = "nozzle_diameter = 0.4\nfilament_diameter = 1.75\n"
    assert sx.drivable_extruder_count(ini) == 1
    # A second nozzle without a matching filament diameter is not a second extruder.
    assert sx.drivable_extruder_count("nozzle_diameter = 0.4,0.4\nfilament_diameter = 1.75\n") == 1
    assert sx.drivable_extruder_count("nozzle_diameter = 0.4\nfilament_diameter = 1.75,1.75\n") == 1
    assert sx.drivable_extruder_count(TWO) == 2


def test_two_extruder_ini_sets_prusaslicer_292_support_keys():
    prof = _profile(TWO)
    out, info = sx.apply(prof, [{"kind": "enforce", "filament_slot": 2}], filament_slots=2)
    assert info["can_drive"] is True and info["applied"] is True and info["extruder"] == 2
    assert "support_material_extruder = 2" in out.ini
    assert "support_material_interface_extruder = 2" in out.ini
    # 2.9.2 has no bottom-interface extruder key. Do not invent one.
    assert "support_material_bottom_interface_extruder" not in out.ini
    same, same_info = sx.apply(prof, [{"kind": "enforce", "filament_slot": "same"}], filament_slots=2)
    assert same_info["extruder"] == 0
    assert "support_material_extruder = 0" in same.ini
    assert "support_material_interface_extruder = 0" in same.ini
    named, named_info = sx.apply(prof, [{"kind": "enforce", "filament_slot": "pva"}], filament_slots=2)
    assert named_info["applied"] is False and named_info["ignored"] is True
    assert "support_material_extruder" not in named.ini
    assert "filament name" in named_info["message"].lower()


def test_one_extruder_ini_does_not_pretend_a_second():
    prof = _profile("nozzle_diameter = 0.4\nfilament_diameter = 1.75\n")
    for slot in (2, "2", "pva", "hips"):
        out, info = sx.apply(prof, [{"kind": "enforce", "filament_slot": slot}], filament_slots=1)
        assert info["can_drive"] is False and info["applied"] is False and info["ignored"] is True
        assert info["message"] == sx.ONE_EXTRUDER
        assert "one extruder" in info["message"].lower()
        assert "support_material_extruder" not in out.ini
        assert "support_material_interface_extruder" not in out.ini
    multi, multi_info = sx.apply(prof, [{"kind": "enforce", "filament_slot": 2}], filament_slots=4)
    assert multi_info["message"] == sx.CANNOT_DRIVE
    assert "cannot drive a second extruder" in multi_info["message"].lower()
    assert "support_material_extruder" not in multi.ini
    same, same_info = sx.apply(prof, [{"kind": "enforce", "filament_slot": "same"}], filament_slots=1)
    assert same_info["ignored"] is False and same_info["applied"] is False
    assert "support_material_extruder" not in same.ini


def test_catalog_picker_follows_the_ini_zeim_loads():
    cat = ps.public()
    saw_multi_slot = False
    for row in cat["printers"]:
        sf = row["support_filament"]
        slots = row["filament_slots"]
        if row["technology"] == "Resin" or not row["nozzles"]:
            assert sf == sx.idle(slots)
            assert "one extruder" in sf["message"].lower()
            assert sf["choices"] == []
            continue
        nozzle = row["stock_nozzle_mm"] or row["nozzles"][0]
        try:
            prof, _settings = eng.profile_for(row["id"], nozzle, {})
        except eng.SliceError:
            assert sf == sx.idle(slots)
            continue
        assert sf == sx.status(prof.ini, slots)
        assert "support_material_extruder" not in prof.ini
        if slots <= 1:
            assert sf["can_drive"] is False
            assert sf["message"] == sx.ONE_EXTRUDER
            assert sf["choices"] == []
        elif not sf["can_drive"]:
            saw_multi_slot = True
            assert sf["message"] == sx.CANNOT_DRIVE
            assert sf["choices"] == []
            out, info = sx.apply(
                prof, [{"kind": "enforce", "filament_slot": "pva"}], filament_slots=slots)
            assert info["ignored"] is True
            assert "support_material_extruder" not in out.ini
        else:
            out, info = sx.apply(
                prof, [{"kind": "enforce", "filament_slot": 2}], filament_slots=slots)
            assert info["applied"] is True and info["extruder"] == 2
            assert "support_material_extruder = 2" in out.ini
            assert "support_material_interface_extruder = 2" in out.ini
    assert saw_multi_slot, "expected at least one AMS/MMU printer the slicer still cannot drive"


def test_k1_and_ams_slice_do_not_emit_a_fake_support_extruder(monkeypatch):
    seen = {}

    def fake_slice(model, profile, out_gcode, *, bounds_stl=None, parts=None):
        seen["ini"] = profile.ini
        out_gcode.write_text(
            "; estimated printing time (normal mode) = 1m 0s\n; total filament used [g] = 1.5\nT1\nG1 X1 Y1 E0.2\n")
        return eng.SliceResult(out_gcode, 60, 1.5, (12.0, 12.0, 6.0), profile)

    monkeypatch.setattr(eng, "slice_model_path", fake_slice)
    client = TestClient(app)
    stl = _box_stl()
    paint = json.dumps([{"kind": "enforce", "x": 1, "y": 1, "r": 3, "filament_slot": "pva"}])
    k1 = client.post("/api/slice", data={
        "printer_id": "creality_k1", "nozzle": "0.4", "supports": "auto", "material": "PLA",
        "support_paint": paint,
    }, files={"file": ("t.stl", stl, "model/stl")})
    assert k1.status_code == 200, k1.text
    body = k1.json()["support_paint"]["support_filament"]
    assert body["can_drive"] is False and body["ignored"] is True
    assert body["message"] == sx.ONE_EXTRUDER
    assert "support_material_extruder" not in seen["ini"]
    assert "nozzle_diameter = 0.4\n" in seen["ini"]
    assert "nozzle_diameter = 0.4,0.4" not in seen["ini"]
    k1_gcode = client.get(k1.json()["gcode_url"]).text
    assert not re.search(r"^T1\b", k1_gcode, re.M)

    paint2 = json.dumps([{"kind": "enforce", "x": 1, "y": 1, "r": 3, "filament_slot": 2}])
    x1 = client.post("/api/slice", data={
        "printer_id": "bambu_x1c", "nozzle": "0.4", "supports": "auto", "material": "PLA",
        "support_paint": paint2,
    }, files={"file": ("t.stl", stl, "model/stl")})
    assert x1.status_code == 200, x1.text
    xbody = x1.json()["support_paint"]["support_filament"]
    assert xbody["message"] == sx.CANNOT_DRIVE
    assert "support_material_extruder" not in seen["ini"]
    assert "support_material_interface_extruder" not in seen["ini"]
    x1_gcode = client.get(x1.json()["gcode_url"]).text
    assert not re.search(r"^T1\b", x1_gcode, re.M)


def test_slice_sets_support_keys_when_the_profile_has_two_extruders(monkeypatch):
    """The slice path, not only the helper: a profile that really lists two extruders gets the keys."""
    real = eng.profile_for

    def two_extruders(*args, **kwargs):
        prof, settings = real(*args, **kwargs)
        text = prof.ini.replace("nozzle_diameter = 0.4\n", "nozzle_diameter = 0.4,0.4\n", 1)
        text = re.sub(r"filament_diameter = ([0-9.]+)\n", r"filament_diameter = \1,\1\n", text, count=1)
        return replace(prof, ini=text), settings

    seen = {}

    def fake_slice(model, profile, out_gcode, *, bounds_stl=None, parts=None):
        seen["ini"] = profile.ini
        out_gcode.write_text(
            "; estimated printing time (normal mode) = 1m 0s\n; total filament used [g] = 1.5\nT1\nG1 X1 Y1 E0.2\n")
        return eng.SliceResult(out_gcode, 60, 1.5, (12.0, 12.0, 6.0), profile)

    monkeypatch.setattr(eng, "profile_for", two_extruders)
    monkeypatch.setattr(eng, "slice_model_path", fake_slice)
    client = TestClient(app)
    paint = json.dumps([{"kind": "enforce", "x": 1, "y": 1, "r": 3, "filament_slot": 2}])
    res = client.post("/api/slice", data={
        "printer_id": "creality_k1", "nozzle": "0.4", "supports": "auto", "material": "PLA",
        "support_paint": paint,
    }, files={"file": ("t.stl", _box_stl(), "model/stl")})
    assert res.status_code == 200, res.text
    info = res.json()["support_paint"]["support_filament"]
    assert info["can_drive"] is True and info["applied"] is True and info["extruder"] == 2
    assert "support_material_extruder = 2" in seen["ini"]
    assert "support_material_interface_extruder = 2" in seen["ini"]
    assert "support_material_bottom_interface_extruder" not in seen["ini"]
    assert sx.drivable_extruder_count(seen["ini"]) == 2
    assert 2 in res.json()["slots"]
    gcode = client.get(res.json()["gcode_url"]).text
    assert re.search(r"^T1\b", gcode, re.M)


def test_picker_source_has_no_pretend_pva_slot():
    js = (ROOT / "static" / "supportpaint.js").read_text()
    printer = (ROOT / "static" / "printer.js").read_text()
    assert "PVA (dissolve)" not in js
    assert 'value="pva"' not in js
    assert 'value="hips"' not in js
    assert "Slot 2" not in js
    assert "This printer has one extruder." in js
    assert "can_drive" in js and "supportFilament" in js
    assert "support_filament" in printer
    assert "mountPaint($(\"#spPaintHost\"), printerOf(P.pref.printer_id)?.support_filament)" in printer
