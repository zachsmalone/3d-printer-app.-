"""Single-slot / slot-subset exports: only the picked (and actually used) CFS/AMS slots are referenced."""
import json
import re
import zipfile
import io

import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient

from app.core import exporters
from app.core.geometry import Body, Model
from app.services import filament_slots as fs
from app.services import universal_export as ue


def _body(name, color=None, dx=0):
    m = trimesh.creation.box((10, 10, 5)); m.apply_translation([dx, 0, 2.5])
    return Body(name, np.asarray(m.vertices, float), np.asarray(m.faces, np.int64), color)


def _read(data):
    z = zipfile.ZipFile(io.BytesIO(data))
    return {n: z.read(n).decode() for n in z.namelist()}


def _extruders(files):
    return [int(v) for v in re.findall(r'key="extruder" value="(\d+)"', files["Metadata/model_settings.config"])]


def test_parse_slots():
    assert fs.parse_slots(None) == [1] and fs.parse_slots("") == [1]
    assert fs.parse_slots("3,1,3") == [1, 3]
    with pytest.raises(ValueError):
        fs.parse_slots("0")
    with pytest.raises(ValueError):
        fs.parse_slots("x")


@pytest.mark.parametrize("slots,expect", [(None, [1]), ([2], [2]), ([1, 3], [1]), ([2, 4], [2])])
def test_single_colour_3mf_references_one_slot(slots, expect):
    files = _read(exporters.to_3mf(Model([_body("a", "#ff0000")], "edit"), "t", slots=slots))
    info = json.loads(files["Metadata/zeim_slots.json"])
    assert info["slots"] == expect and info["filament_to_slot"] == {"1": expect[0]}
    assert files["3D/3dmodel.model"].count("<base ") == 1
    assert _extruders(files) == [1]
    if slots and len(slots) > 1:
        assert info["notes"] and "left out" in info["notes"][0]        # a note, never an error


def test_colourless_mesh_export_slot_2():
    data, ext, _ = ue.export_mesh_data(trimesh.creation.box((10, 10, 10)), "3mf")
    files = _read(fs.annotate_3mf(data, fs.plan([], [2])))
    assert json.loads(files["Metadata/zeim_slots.json"])["slots"] == [2]
    assert set(_extruders(files)) == {1}
    assert 'Extension="config"' in files["[Content_Types].xml"]


def test_two_colour_model_with_slots_1_and_3():
    m = Model([_body("red", "#FF0000"), _body("blue", "#0000FF", 20)], "layers")
    files = _read(exporters.to_3mf(m, "t", slots=[1, 3]))
    info = json.loads(files["Metadata/zeim_slots.json"])
    assert info["slots"] == [1, 3] and info["filament_to_slot"] == {"1": 1, "2": 3}
    assert files["3D/3dmodel.model"].count("<base ") == 2
    assert sorted(_extruders(files)) == [1, 2]


def test_three_colours_two_slots_folds_and_warns():
    m = Model([_body("r", "#FF0000"), _body("g", "#00FF00", 20), _body("b", "#0000FF", 40)], "layers")
    files = _read(exporters.to_3mf(m, "t", slots=[2, 4]))
    info = json.loads(files["Metadata/zeim_slots.json"])
    assert info["slots"] == [2, 4] and max(_extruders(files)) == 2
    assert files["3D/3dmodel.model"].count("<base ") == 2
    assert any("continue" in n for n in info["notes"])


def _slice(client, stl, slots):
    r = client.post("/api/slice", data={"printer_id": "creality_k1", "nozzle": "0.4", "supports": "off",
                                        "material": "PLA", "slots": slots},
                    files={"file": ("t.stl", stl, "application/sla")})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("slots,expect", [("1", [1]), ("2", [2]), ("1,3", [1])])
def test_gcode_single_material_no_tool_changes(slots, expect):
    from app.services import slicer
    if not slicer.status()["available"]:
        pytest.skip("PrusaSlicer not available")
    client = TestClient(app_())
    body = _slice(client, trimesh.creation.box((15, 15, 6)).export(file_type="stl"), slots)
    assert body["slots"] == expect
    g = client.get(body["gcode_url"]).text
    assert f"; ZEIM filament slots used: {','.join(map(str, expect))}" in g
    assert not re.search(r"^T\d+", g, re.M)                                  # no tool changes / slot selects
    assert not re.search(r"^M10[49]\b.*\bT\d", g, re.M)                      # no per-extruder temperatures
    assert not re.search(r"^(M600|M701|M702)\b", g, re.M)                    # no filament change / load macros
    fc = re.search(r"^; filament_colour = (.*)$", g, re.M).group(1)
    assert ";" not in fc                                                     # one filament in the config block
    files = _read(client.get(f"/api/slice/{body['slice_id']}/model.3mf").content)
    assert json.loads(files["Metadata/zeim_slots.json"])["slots"] == expect


def test_slice_rejects_bad_slot():
    r = TestClient(app_()).post("/api/slice", data={"printer_id": "creality_k1", "slots": "9x"},
                                files={"file": ("t.stl", trimesh.creation.box((5, 5, 5)).export(file_type="stl"), "application/sla")})
    assert r.status_code == 400


def app_():
    from app.main import app
    return app


def test_plan_heads_only_lists_used_slots_with_filament_and_colour():
    p = fs.plan_heads("1,3", '["PLA","PETG"]', '["#ff0000","#0033aa"]')
    assert p["slots"] == [1, 3]
    assert p["materials"] == ["PLA", "PETG"]
    assert p["colours"] == ["#FF0000", "#0033AA"]
    assert "1, 3" in p["notes"][0] and "not heated" in p["notes"][0]


def test_gcode_header_and_strip_unused_heads():
    p = fs.plan_heads("2", "PETG", "#00FF00")
    h = fs.gcode_header(p)
    assert "; ZEIM filament slots used: 2" in h
    assert "; ZEIM slot 2: PETG #00FF00" in h
    assert "only listed slots are heated" in h
    junk = "; prelude\nT0\nT1\nM104 S220 T0\nM104 S220 T3\nM109 S220\nG1 X1\nM600\nM701 T4\n"
    out = fs.strip_unused_heads(junk, p)
    assert "T0" not in out and "T1" not in out and "M600" not in out and "M701" not in out
    assert "M109 S220" in out and "G1 X1" in out
    # multi: keep tools for used slots only (0-based T0/T1 for slots 1+2)
    multi = fs.strip_unused_heads(junk, fs.plan_heads("1,2"))
    assert "T0" in multi and "T1" in multi
    assert "M104 S220 T3" not in multi and "M701" not in multi


def test_slot_count_for_systems():
    assert fs.slot_count_for_systems([]) == 1
    assert fs.slot_count_for_systems(["AMS"]) == 4
    assert fs.slot_count_for_systems(["MMU3"]) == 5
