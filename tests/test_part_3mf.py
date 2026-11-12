"""Part filament slots in the 3MF used by FDM and CAD.

A one-slot printer keeps a single object. More slots write each part's slot into
the extruder metadata PrusaSlicer, OrcaSlicer, Bambu Studio and Creality Print
document. Re-importing that file keeps the part names and slots.

When the PrusaSlicer CLI is installed, one test slices the together export with
two extruders and checks that both T0 and T1 are in the G-code. It does not open
the slicer window, and nothing here has been sent to a printer.
"""
import io
import json
import os
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


def _triangle_count(model_xml: str) -> int:
    return model_xml.count("<triangle ")


def _together_volumes(slic3r: str) -> list[tuple[int, int, int]]:
    """(firstid, lastid, extruder) for each volume, in file order."""
    spans = []
    for vol in re.finditer(r"<volume\b([^>]*)>(.*?)</volume>", slic3r, re.S):
        attrs, body = vol.group(1), vol.group(2)
        first = int(re.search(r'firstid="(\d+)"', attrs).group(1))
        last = int(re.search(r'lastid="(\d+)"', attrs).group(1))
        extruder = int(re.search(r'type="volume" key="extruder" value="(\d+)"', body).group(1))
        assert 'type="volume" key="volume_type" value="ModelPart"' in body
        assert 'type="volume" key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"' in body
        assert "source_" not in body
        spans.append((first, last, extruder))
    return spans


def _assert_together_mesh(files: dict[str, str], slots: list[int]):
    """The together file is one mesh, and volume ranges partition its triangles."""
    model = files["3D/3dmodel.model"]
    assert model.count("<item ") == 1
    assert "<component " not in model
    assert model.count("<mesh>") == 1
    n = _triangle_count(model)
    spans = _together_volumes(files["Metadata/Slic3r_PE_model.config"])
    assert [slot for _first, _last, slot in spans] == slots
    assert spans[0][0] == 0
    cursor = 0
    for first, last, _slot in spans:
        assert first == cursor and last >= first
        cursor = last + 1
    assert cursor == n
    settings = files["Metadata/model_settings.config"]
    assert settings.count('subtype="normal_part"') == len(slots)
    assert "firstid=" not in settings
    assert [int(v) for v in re.findall(r'<part\b[^>]*>.*?<metadata key="extruder" value="(\d+)"', settings, re.S)] == slots


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
    _assert_together_mesh(files, [1, 4])
    assert "Left" in files["Metadata/model_settings.config"]
    assert "Right" in files["Metadata/Slic3r_PE_model.config"]


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
    _assert_together_mesh(files, [1, 2, 3, 4])
    assert 'displaycolor="#FF0000FF"' in model
    assert 'displaycolor="#00FF00FF"' in model
    assert 'displaycolor="#0000FFFF"' in model
    settings = files["Metadata/model_settings.config"]
    slic3r = files["Metadata/Slic3r_PE_model.config"]
    for name in ("Box", "Peg", "Ball"):
        assert name in settings and name in slic3r
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
    assert "Left" in cached_files["Metadata/Slic3r_PE_model.config"]
    assert "Right" in cached_files["Metadata/model_settings.config"]
    assert 3 in _extruders(cached_files["Metadata/model_settings.config"])


def _prusa_exe() -> str | None:
    env = os.environ.get("PRUSA_SLICER") or ""
    if env and os.path.isfile(env) and os.access(env, os.X_OK):
        return env
    return shutil.which("prusa-slicer") or shutil.which("prusa-slicer-console") or shutil.which("PrusaSlicer")


# Two physical extruders. PrusaSlicer counts them from nozzle_diameter and filament_diameter
# (see its 3mf reader and PrintConfig). single_extruder_multi_material stays off so the
# slice emits T0/T1 rather than a single-nozzle filament-change macro.
_TWO_EXTRUDER = """
printer_technology = FFF
bed_shape = 0x0,200x0,200x200,0x200
nozzle_diameter = 0.4,0.4
filament_diameter = 1.75,1.75
extruder_offset = 0x0,0x0
single_extruder_multi_material = 0
wipe_tower = 0
gcode_flavor = marlin2
layer_height = 0.3
first_layer_height = 0.3
perimeters = 1
top_solid_layers = 1
bottom_solid_layers = 1
fill_density = 0%
skirts = 0
support_material = 0
temperature = 210,210
first_layer_temperature = 210,210
bed_temperature = 60
first_layer_bed_temperature = 60
filament_type = PLA;PLA
filament_density = 1.24,1.24
filament_colour = #FF0000;#0000FF
extruder_colour = #FF0000;#0000FF
"""


def _tool_counts(gcode: str) -> tuple[int, int]:
    body = [line.split(";", 1)[0].strip() for line in gcode.splitlines()]
    t0 = sum(1 for line in body if re.match(r"T0\b", line, re.I))
    t1 = sum(1 for line in body if re.match(r"T1\b", line, re.I))
    return t0, t1


def test_prusaslicer_together_slice_uses_both_extruders(tmp_path):
    """Together packing: one object, one volume per part. Both extruders must tool-change.

    Skipped when the PrusaSlicer CLI is not installed. Set PRUSA_SLICER to the binary
    when it is not on PATH.
    """
    exe = _prusa_exe()
    if not exe:
        pytest.skip("PrusaSlicer CLI is not installed")
    mesh, meta, parts = _project(_apart_3mf())
    # The imported boxes straddle y = 0. PrusaSlicer 2.9 rejects a model that hangs
    # off a corner-origin bed, so shift them onto the bed before export.
    mesh.apply_translation((40, 40, 0))
    parts[0]["slot"] = 1
    parts[1]["slot"] = 2
    meta["parts"] = parts
    assert part3mf.stays_together(mesh, parts, meta)
    baked = part3mf.build(mesh, meta, 2)
    assert baked is not None
    _assert_together_mesh(_files(baked[0]), [1, 2])
    src = tmp_path / "together.3mf"
    src.write_bytes(baked[0])
    ini = tmp_path / "two-extruder.ini"
    ini.write_text(_TWO_EXTRUDER)
    gcode = tmp_path / "together.gcode"
    home = tmp_path / "home"
    home.mkdir()
    proc = subprocess.run(
        [exe, "--load", str(ini), "--export-gcode", "--output", str(gcode), str(src)],
        capture_output=True, text=True, timeout=180,
        env={**os.environ, "HOME": str(home)},
    )
    assert proc.returncode == 0, (proc.stdout or "")[-800:] + (proc.stderr or "")[-800:]
    text = gcode.read_text(errors="replace")
    t0, t1 = _tool_counts(text)
    assert t0 > 0 and t1 > 0, f"T0={t0} T1={t1}"
    used = re.search(r"filament used \[mm\] = ([0-9., ]+)", text)
    assert used, text[:500]
    amounts = [float(x) for x in used.group(1).replace(" ", "").split(",") if x]
    assert len(amounts) >= 2 and amounts[0] > 0 and amounts[1] > 0, amounts
    # Re-export is how the bug showed up: PrusaSlicer dropped every extruder key.
    again_path = tmp_path / "again.3mf"
    again = subprocess.run(
        [exe, "--export-3mf", "--output", str(again_path), str(src)],
        capture_output=True, text=True, timeout=90,
        env={**os.environ, "HOME": str(home)},
    )
    assert again.returncode == 0, (again.stdout or "")[-400:] + (again.stderr or "")[-400:]
    rewritten = _files(again_path.read_bytes())["Metadata/Slic3r_PE_model.config"]
    assert 'type="volume" key="extruder" value="1"' in rewritten
    assert 'type="volume" key="extruder" value="2"' in rewritten


def test_prusaslicer_opens_the_export(tmp_path):
    exe = _prusa_exe()
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
