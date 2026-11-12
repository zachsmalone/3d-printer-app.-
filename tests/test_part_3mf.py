"""Part filament slots in the 3MF used by FDM and CAD.

A one-slot printer keeps a single object. More slots write each part's slot into
the extruder metadata PrusaSlicer, OrcaSlicer, Bambu Studio and Creality Print
document. Re-importing that file keeps the part names and slots.

PrusaSlicer --info runs only when the CLI is installed. It checks that the
package opens. It does not prove a slicer UI assigned the extruders, and nothing
here has been sent to a printer.
"""
import io
import json
import re
import shutil
import subprocess
import zipfile

import pytest
import trimesh

from app.api import slice as slice_api
from app.core import exporters, meshparts, part3mf
from app.core.exporters import mesh_3mf
from app.core.geometry import Body, Model
from app.services import filament_slots as fs
from tests.test_mesh_parts import _3mf, _box, _coloured_3mf, _mesh_xml


def _apart_3mf():
    left = _box((10, 10, 10), (0, 0, 5))
    right = _box((10, 10, 10), (40, 0, 5))
    return _3mf(
        [_mesh_xml(left, 1, "Left"), _mesh_xml(right, 2, "Right")],
        ['<item objectid="1"/>', '<item objectid="2"/>'],
    )


def _files(data: bytes) -> dict[str, str]:
    zipped = zipfile.ZipFile(io.BytesIO(data))
    return {name: zipped.read(name).decode() for name in zipped.namelist()}


def _loaded(data: bytes):
    mesh, parts, _warnings = meshparts.load_document(data, "3mf", split_shells=True)
    return mesh, parts


def _project(data: bytes, meta: dict | None = None):
    mesh, parts, _warnings = meshparts.load_document(data, "3mf", split_shells=True)
    base = {"head": 0, "ops": [], "base": {"type": "upload", "format": "3mf"}, "parts": parts}
    if meta:
        base.update(meta)
        base["parts"] = parts
    return mesh, base, parts


def _extruders(xml: str) -> list[int]:
    return [int(v) for v in re.findall(r'key="extruder" value="(\d+)"', xml)]


def test_missing_slot_is_1_and_a_high_slot_is_clamped():
    mesh, meta, parts = _project(_apart_3mf())
    parts[0]["slot"] = None
    parts[1]["slot"] = 9
    meta["parts"] = parts
    baked = part3mf.build(mesh, meta, 4)
    assert baked is not None
    data, slots = baked
    assert slots == [1, 4]
    files = _files(data)
    assert "Left" in files["3D/3dmodel.model"] and "Right" in files["3D/3dmodel.model"]
    assert 1 in _extruders(files["Metadata/model_settings.config"])
    assert 4 in _extruders(files["Metadata/model_settings.config"])
    assert 1 in _extruders(files["Metadata/Slic3r_PE_model.config"])
    assert 4 in _extruders(files["Metadata/Slic3r_PE_model.config"])


def test_overlapping_or_unarranged_parts_share_one_object():
    mesh, meta, parts = _project(_coloured_3mf())
    for part, slot in zip(parts, (1, 2, 3, 4)):
        part["slot"] = slot
    meta["parts"] = parts
    assert part3mf.stays_together(mesh, parts, meta)
    baked = part3mf.build(mesh, meta, 4)
    assert baked is not None
    data, slots = baked
    assert slots == [1, 2, 3, 4]
    files = _files(data)
    model = files["3D/3dmodel.model"]
    assert model.count("<item ") == 1
    assert model.count("<component ") == len(parts)
    assert 'displaycolor="#FF0000FF"' in model
    assert 'displaycolor="#00FF00FF"' in model
    assert 'displaycolor="#0000FFFF"' in model
    settings = files["Metadata/model_settings.config"]
    slic3r = files["Metadata/Slic3r_PE_model.config"]
    for name in ("Box", "Peg", "Ball"):
        assert name in settings and name in slic3r and name in model
    assert sorted(_extruders(settings)) == [1, 1, 2, 3, 4]
    assert sorted(set(_extruders(slic3r))) == [1, 2, 3, 4]
    _mesh, back = _loaded(data)
    got = sorted((p["name"], p["slot"], p["color"]) for p in back)
    want = sorted((p["name"], p["slot"], p["color"]) for p in parts)
    assert got == want


def test_arranged_parts_that_do_not_overlap_are_separate_objects():
    mesh, meta, parts = _project(_apart_3mf())
    parts[0]["slot"] = 2
    parts[1]["slot"] = 3
    meta.update({"head": 1, "ops": [{"op": "plate"}], "base": {"type": "plate"}, "parts": parts})
    assert slice_api.arranged_on_bed(meta)
    assert not part3mf.stays_together(mesh, parts, meta)
    baked = part3mf.build(mesh, meta, 4)
    assert baked is not None
    data, slots = baked
    assert slots == [2, 3]
    files = _files(data)
    assert files["3D/3dmodel.model"].count("<item ") == 2
    assert "<component " not in files["3D/3dmodel.model"]
    assert _extruders(files["Metadata/model_settings.config"]) == [2, 3]
    assert 2 in _extruders(files["Metadata/Slic3r_PE_model.config"])
    assert 3 in _extruders(files["Metadata/Slic3r_PE_model.config"])
    _mesh, back = _loaded(data)
    assert [(p["name"], p["slot"]) for p in back] == [("Left", 2), ("Right", 3)]


def test_one_slot_keeps_todays_single_object_file():
    mesh, meta, parts = _project(_apart_3mf())
    parts[0]["slot"] = 2
    parts[1]["slot"] = 3
    meta["parts"] = parts
    assert part3mf.build(mesh, meta, 1) is None
    assert part3mf.stored_slot_count([{"slot": 1}, {"slot": 1}]) == 1
    assert part3mf.stored_slot_count(parts) == 16
    old = fs.annotate_3mf(mesh_3mf(mesh.vertices, mesh.faces), fs.plan([], [1]))
    files = _files(old)
    assert files["3D/3dmodel.model"].count("<object ") == 1
    assert "Slic3r_PE_model.config" not in files
    box = trimesh.creation.box((8, 8, 8))
    plain = exporters.to_3mf(Model([Body("a", box.vertices, box.faces)], "edit"))
    _mesh, back = _loaded(plain)
    assert len(back) == 1 and back[0]["slot"] is None


def test_join_decision_matches_the_slice_path():
    a = trimesh.creation.box((10, 10, 10))
    b = a.copy()
    b.apply_translation((40, 0, 0))
    peg = a.copy()
    peg.apply_translation((4, 0, 0))
    imported = {"head": 0, "ops": [], "base": {"type": "upload"}}
    arranged = {"head": 1, "ops": [{"op": "plate"}], "base": {"type": "plate"}}
    assert part3mf._arranged(imported) is slice_api.arranged_on_bed(imported)
    assert part3mf._arranged(arranged) is slice_api.arranged_on_bed(arranged)
    assert part3mf._bounds_intersect([a, b]) is slice_api.bounds_intersect([a, b])
    assert part3mf._bounds_intersect([a, peg]) is slice_api.bounds_intersect([a, peg])


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import config
    from app.main import app
    from app.services import editproj
    from app.services.history import store

    monkeypatch.setattr(config, "DATA", tmp_path / "data")
    monkeypatch.setattr(store, "root", tmp_path / "outputs")
    (tmp_path / "outputs").mkdir()
    editproj._BASES.clear()
    editproj._STATES.clear()
    store.cache.clear()
    yield TestClient(app)
    editproj._BASES.clear()
    editproj._STATES.clear()
    store.cache.clear()


def _assign(client, bid, part_id, slot):
    got = client.put(f"/api/edit/{bid}/parts/slots", json={
        "action": "assign", "ids": [part_id], "slot": slot, "slot_count": 4,
    })
    assert got.status_code == 200, got.text
    return got.json()["parts"]


def test_export_round_trip_and_single_slot_printer(client):
    opened = client.post("/api/edit/new", files={"file": ("apart.3mf", _apart_3mf(), "model/3mf")},
                         data={"printer_id": "bambu_x1c"})
    assert opened.status_code == 200, opened.text
    body = opened.json()
    bid = body["id"]
    ids = [p["id"] for p in body["parts"]]
    assert len(ids) == 2
    _assign(client, bid, ids[0], 1)
    saved = _assign(client, bid, ids[1], 3)
    assert [p["slot"] for p in saved] == [1, 3]

    single = client.get(f"/api/export/{bid}/download?format=3mf&printer_id=creality_k1")
    assert single.status_code == 200, single.text
    single_files = _files(single.content)
    assert single_files["3D/3dmodel.model"].count("<object ") == 1
    assert "Slic3r_PE_model.config" not in single_files
    assert "Left" not in single_files["3D/3dmodel.model"]

    exported = client.get(f"/api/export/{bid}/download?format=3mf&printer_id=bambu_x1c")
    assert exported.status_code == 200, exported.text
    assert exported.headers["x-export-slots"] == "1,3"
    files = _files(exported.content)
    assert "Left" in files["Metadata/model_settings.config"]
    assert "Right" in files["Metadata/model_settings.config"]
    assert _extruders(files["Metadata/model_settings.config"]) == [1, 1, 3]
    assert 1 in _extruders(files["Metadata/Slic3r_PE_model.config"])
    assert 3 in _extruders(files["Metadata/Slic3r_PE_model.config"])
    info = json.loads(files["Metadata/zeim_slots.json"])
    assert [p["slot"] for p in info["parts"]] == [1, 3]
    assert "Not confirmed on a printer." in info["notes"]

    again = client.post(
        "/api/edit/new",
        files={"file": ("round.3mf", exported.content, "model/3mf")},
        data={"printer_id": "bambu_x1c"},
    )
    assert again.status_code == 200, again.text
    back = again.json()["parts"]
    assert [(p["name"], p["slot"]) for p in back] == [("Left", 1), ("Right", 3)]

    cached = client.get(f"/api/download/{bid}/3mf")
    assert cached.status_code == 200
    cached_files = _files(cached.content)
    assert "Left" in cached_files["3D/3dmodel.model"]
    assert 3 in _extruders(cached_files["Metadata/model_settings.config"])


def test_prusaslicer_opens_the_export(tmp_path):
    exe = shutil.which("prusa-slicer") or shutil.which("prusa-slicer-console") or shutil.which("PrusaSlicer")
    if not exe:
        pytest.skip("PrusaSlicer CLI is not installed")
    mesh, meta, parts = _project(_apart_3mf())
    parts[0]["slot"] = 1
    parts[1]["slot"] = 2
    meta["parts"] = parts
    baked = part3mf.build(mesh, meta, 4)
    assert baked is not None
    dest = tmp_path / "parts.3mf"
    dest.write_bytes(baked[0])
    proc = subprocess.run([exe, "--info", str(dest)], capture_output=True, text=True, timeout=90)
    assert proc.returncode == 0, (proc.stdout or "")[-400:] + (proc.stderr or "")[-400:]
