"""Single-slot FDM output: one tool command, no leveling macro, one filament in the file.

The slicer is stubbed. A real PrusaSlicer run lives in test_filament_slots and skips when the CLI is absent.
"""
import io
import json
import re
import zipfile
from pathlib import Path

import trimesh
from fastapi.testclient import TestClient

from app.main import app
from app.printers import list_printers, load_printer
from app.services import filament_slots as fs
from app.services import print_setup as ps
from app.services import single_slot as ss
from app.services import slice_engine as eng

_SYSTEMS = {"CFS", "AMS", "AMS lite", "MMU3", "ACE Pro"}


def _box() -> bytes:
    return trimesh.creation.box(extents=(12, 12, 6)).export(file_type="stl")


def _fake_engine(monkeypatch, body: str, seen: dict):
    def fake_slice(model, profile, out_gcode, *, bounds_stl=None, parts=None):
        seen["ini"] = profile.ini
        out_gcode.write_text(body)
        return eng.SliceResult(out_gcode, 60, 1.2, (12.0, 12.0, 6.0), profile)

    monkeypatch.setattr(eng, "slice_model_path", fake_slice)


def test_catalog_option_matches_known_families_and_stays_unverified():
    assert ss.option_for("creality_k1")["family"] == "creality_cfs"
    assert ss.option_for("creality_k1")["slots"] == 4
    assert ss.option_for("creality_k2")["family"] == "creality_cfs"
    assert ss.option_for("creality_k1_max")["slots"] == 4
    assert ss.option_for("bambu_x1c")["family"] == "bambu_ams"
    assert ss.option_for("bambu_a1")["family"] == "bambu_ams"
    assert ss.option_for("prusa_mk4")["family"] == "prusa_mmu"
    assert ss.option_for("prusa_mk4")["slots"] == 5
    assert ss.option_for("anycubic_kobra3")["family"] == "anycubic_ace"
    assert ss.option_for("creality_ender3_v3") is None
    for pid in list_printers():
        systems = load_printer(pid)["settings"].get("multi_color_system", {}).get("value") or []
        opt = ss.option_for(pid)
        known = pid in ss.CREALITY_CFS_IDS or any(s in _SYSTEMS for s in systems)
        if known:
            assert opt["default_on"] is True and opt["hardware_verified"] is False
            assert opt["label"] == ss.LABEL
            assert "not printed" in opt["note"].lower() or "has not printed" in opt["note"]
        else:
            assert opt is None
    k1 = ps.printer_public("creality_k1")
    assert k1["filament_slots"] == 1 and k1["multi_color_system"] == []
    assert k1["single_slot_option"]["family"] == "creality_cfs"
    assert ps.printer_public("creality_ender3_v3")["single_slot_option"] is None


def test_resolve_is_on_by_default_for_one_slot_and_off_otherwise():
    plan = fs.plan_heads("2", "PLA", "#00FF00")
    spec = ss.resolve("creality_k1", plan, None)
    assert spec["tool"] == "T1" and spec["slot"] == 2 and spec["hardware_verified"] is False
    assert ss.resolve("creality_k1", plan, False) is None
    assert ss.resolve("creality_k1", fs.plan_heads("1,3"), None) is None
    assert ss.resolve("creality_ender3_v3", plan, None) is None
    assert ss.resolve("prusa_mk4", fs.plan_heads("5"), True)["tool"] == "T4"
    try:
        ss.resolve("creality_k1", fs.plan_heads("5"), True)
    except ValueError as e:
        assert "1–4" in str(e) or "1-4" in str(e)
    else:
        raise AssertionError("slot 5 should be refused on a CFS printer")


def test_finish_gcode_keeps_one_tool_and_drops_leveling():
    spec = ss.resolve("creality_k2", fs.plan_heads("2"), True)
    raw = "\n".join([
        "; filament_colour = #111111;#222222;#333333;#444444",
        "; filament_type = PLA;PETG;ABS;TPU",
        "START_PRINT EXTRUDER_TEMP=210 BED_TEMP=60",
        "G29 A",
        "G29.1",
        "BED_MESH_CALIBRATE",
        "CX_PRINT_LEVELING_CALIBRATION",
        "PRINT_CALIBRATION",
        "T0",
        "T1",
        "T1",
        "T3",
        "M620 S0A",
        "G1 X1",
        "; start_gcode = START_PRINT EXTRUDER_TEMP=210",
        "; G29 stays in a comment",
        "",
    ]) + "\n"
    out = ss.finish_gcode(raw, spec)
    assert re.findall(r"^T\d+", out, re.M) == ["T1"]
    for banned in ("START_PRINT EXTRUDER", "G29", "BED_MESH_CALIBRATE", "CX_PRINT_LEVELING_CALIBRATION",
                   "PRINT_CALIBRATION", "M620", "T0", "T3"):
        assert not re.search(rf"^{banned}\b", out, re.M), banned
    assert "; start_gcode = START_PRINT EXTRUDER_TEMP=210" in out
    assert "; G29 stays in a comment" in out
    assert "; filament_colour = #111111\n" in out
    assert "#222222" not in out
    assert "; filament_type = PLA\n" in out
    assert "G1 X1" in out


def test_finish_inserts_the_family_load_when_the_slicer_emitted_none():
    creality = ss.resolve("creality_k1", fs.plan_heads("1"), None)
    out = ss.finish_gcode("M109 S210\nG28\nG1 X2\n", creality)
    assert out.index("G28") < out.index("T0") < out.index("G1 X2")
    assert "M620" not in out
    bambu = ss.resolve("bambu_x1c", fs.plan_heads("4"), True)
    bout = ss.finish_gcode("G28\nG1 X1\n", bambu)
    assert re.findall(r"^T\d+", bout, re.M) == ["T3"]
    assert "M620 S3A" in bout and "M621 S3A" in bout
    assert bout.index("M620 S3A") < bout.index("T3") < bout.index("M621 S3A")
    prusa = ss.resolve("prusa_mk4", fs.plan_heads("1"), True)
    pout = ss.finish_gcode("G28\nG80\nG29\nT0\nT4\n", prusa)
    assert re.findall(r"^T\d+", pout, re.M) == ["T0"]
    assert not re.search(r"^G80\b", pout, re.M) and not re.search(r"^G29\b", pout, re.M)


def test_slice_api_writes_one_slot_for_k1_and_leaves_leveling_out(monkeypatch):
    seen = {}
    _fake_engine(monkeypatch, seen=seen, body=(
        "; estimated printing time (normal mode) = 1m 0s\n"
        "; total filament used [g] = 1.5\n"
        "; filament_colour = #FFFFFF;#FFFFFF;#FFFFFF;#FFFFFF\n"
        "START_PRINT EXTRUDER_TEMP=210 BED_TEMP=60\n"
        "G29\nT0\nT2\nG1 X1 Y1 E0.1\n"
    ))
    client = TestClient(app)
    res = client.post("/api/slice", data={
        "printer_id": "creality_k1", "nozzle": "0.4", "supports": "off", "material": "PLA", "slots": "3",
    }, files={"file": ("t.stl", _box(), "model/stl")})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["single_slot"] is True and body["slots"] == [3] and body["single_slot_tool"] == "T2"
    assert body["hardware_verified"] is False and body["single_slot_family"] == "creality_cfs"
    assert "has not printed" in body["slot_notes"][0]
    ini = seen["ini"]
    assert "gcode_flavor = klipper" in ini
    assert "machine_limits_usage = time_estimate_only" in ini
    assert "end_gcode = END_PRINT" in ini
    assert "M109 S[first_layer_temperature]" in ini
    assert "M190 S[first_layer_bed_temperature]" in ini
    assert r"\nT2\n" in ini or "\nT2\n" in ini
    assert "START_PRINT" not in ini.split("end_gcode", 1)[-1] or "START_PRINT" not in ini
    assert "START_PRINT" not in ini
    g = client.get(body["gcode_url"]).text
    assert re.findall(r"^T\d+", g, re.M) == ["T2"]
    assert not re.search(r"^START_PRINT\b", g, re.M)
    assert not re.search(r"^G29\b", g, re.M)
    assert "; filament_colour = #FFFFFF\n" in g
    assert "#FFFFFF;" not in g
    assert "not confirmed on a printer" in g
    packed = client.get(f"/api/slice/{body['slice_id']}/model.3mf").content
    files = {n: zipfile.ZipFile(io.BytesIO(packed)).read(n).decode() for n in zipfile.ZipFile(io.BytesIO(packed)).namelist()}
    info = json.loads(files["Metadata/zeim_slots.json"])
    assert info["slots"] == [3] and info["filament_to_slot"] == {"1": 3}
    assert info["single_slot"] is True and info["tool"] == "T2" and info["hardware_verified"] is False
    assert "project_settings.config" not in files
    assert files["Metadata/model_settings.config"].count('key="extruder"') == 1


def test_explicit_off_and_a_second_slot_do_not_rename_the_start(monkeypatch):
    seen = {}
    _fake_engine(monkeypatch, seen=seen, body="T0\nT1\nG1 X1\n")
    client = TestClient(app)
    off = client.post("/api/slice", data={
        "printer_id": "creality_k1", "nozzle": "0.4", "supports": "off", "material": "PLA",
        "slots": "1", "single_slot": "0",
    }, files={"file": ("t.stl", _box(), "model/stl")})
    assert off.status_code == 200, off.text
    assert off.json()["single_slot"] is False
    assert "gcode_flavor = marlin2" in seen["ini"]
    assert "END_PRINT" not in seen["ini"]
    assert not re.search(r"^T\d+", client.get(off.json()["gcode_url"]).text, re.M)
    multi = client.post("/api/slice", data={
        "printer_id": "bambu_x1c", "nozzle": "0.4", "supports": "off", "material": "PLA",
        "slots": "1,3", "slot_materials": '["PLA","PLA"]', "slot_colours": '["#ffffff","#ff0000"]',
        "single_slot": "1",
    }, files={"file": ("t.stl", _box(), "model/stl")})
    assert multi.status_code == 200, multi.text
    assert multi.json()["single_slot"] is False and multi.json()["slots"] == [1, 3]
    assert "M620" not in seen["ini"]


def test_bad_flag_and_slot_past_the_box_are_refused():
    client = TestClient(app)
    bad = client.post("/api/slice", data={
        "printer_id": "creality_k1", "nozzle": "0.4", "single_slot": "maybe",
    }, files={"file": ("t.stl", _box(), "model/stl")})
    assert bad.status_code == 400
    far = client.post("/api/slice", data={
        "printer_id": "creality_k1_max", "nozzle": "0.4", "slots": "5", "single_slot": "1",
    }, files={"file": ("t.stl", _box(), "model/stl")})
    assert far.status_code == 400 and "1" in far.text


def test_filament_tab_markup_is_the_single_slot_control():
    js = (Path(__file__).resolve().parents[1] / "static" / "printer.js").read_text(encoding="utf-8")
    assert "function singleSlotHTML" in js
    assert 'id="spSingleSlot"' in js and 'id="spSingleSlotN"' in js
    assert "single_slot_option" in js
    assert 'fd.append("single_slot"' in js
    assert ss.LABEL in js
    filament = js.split('id="procPane-filament"')[1].split('id="procPane-strength"')[0]
    assert "singleSlotHTML" in filament and "slotsHTML" in filament
    assert "Not confirmed on a printer" in js
