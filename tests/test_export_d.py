"""D: export formats (STL/3MF/OBJ/PLY/GLB/AMF round-trip), safe file names, rename, Back up all, save prefs."""
import io
import json
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
import trimesh

from tests.b1 import client, ADULT, photo_build
from app.services import filenames as fn, universal_export as ue

ROOT = Path(__file__).resolve().parent.parent


def _load_amf(data: bytes) -> trimesh.Trimesh:
    t = ET.fromstring(data)
    assert t.tag == "amf" and t.get("unit") == "millimeter"
    v = [[float(c.find(a).text) for a in "xyz"] for c in t.iter("coordinates")]
    f = [[int(tr.find(k).text) for k in ("v1", "v2", "v3")] for tr in t.iter("triangle")]
    return trimesh.Trimesh(v, f, process=False)


@pytest.mark.parametrize("fmt", list(ue.FORMATS))
def test_every_format_round_trips(fmt):
    m = trimesh.creation.box(extents=[20, 10, 5])
    data, ext, mime = ue.export_mesh_data(m, force_format=fmt)
    assert ext == fmt and mime and len(data) > 50
    if fmt == "amf":
        back = _load_amf(data)
    else:
        back = trimesh.load(io.BytesIO(data), file_type=fmt, force="mesh")
    assert back.extents == pytest.approx([20, 10, 5], abs=1e-3)
    assert back.is_watertight and back.volume == pytest.approx(1000, rel=1e-3)


def test_formats_have_one_line_descriptions_and_no_step():
    j = client().get("/api/export/formats").json()
    ids = [f["id"] for f in j["formats"]]
    assert ids == ["stl", "3mf", "obj", "ply", "glb", "amf"] and "step" not in ids
    assert all(f["desc"] and "\n" not in f["desc"] and len(f["desc"]) < 110 for f in j["formats"])
    assert j["step"] is False and "solid" in j["step_note"]
    with pytest.raises(ValueError):
        ue.export_mesh_data(trimesh.creation.box(), force_format="step")


@pytest.mark.parametrize("raw,want", [
    ('My: "vase"/v2?', "My vase v2"), ("CON", "_CON"), ("nul.txt", "_nul.txt"), ("  ..hidden. ", "hidden"),
    ("a\u202eb\u200bc", "a b c"), ("", "ZEIM model"), ("Größe 漢字 ✓", "Größe 漢字 ✓"), ("x" * 300, "x" * 120),
    ("tab\there|pipe*", "tab here pipe"), ("trailing...", "trailing")])
def test_safe_name(raw, want):
    assert fn.safe_name(raw) == want


def test_default_name_title_printer_layer():
    assert fn.default_stem("Mum's lamp", "Creality K1", 0.2) == "Mum's lamp - Creality K1 - 0.2mm"
    assert fn.default_stem("Box", "Elegoo Saturn", 0.05) == "Box - Elegoo Saturn - 0.05mm"
    assert fn.file_name("Box.STL", "stl") == "Box.stl"
    assert "filename*=UTF-8''" in fn.disposition("Größe.stl")


def test_export_named_rename_and_download():
    c = client(ADULT)
    bid = photo_build(c)
    info = c.get(f"/api/export/{bid}", params={"printer_id": "creality_k1"}).json()
    assert info["name"].endswith(" - Creality K1 - 0.2mm") and info["filenames"]["glb"].endswith(".glb")
    for f in ue.FORMATS:
        r = c.get(f"/api/export/{bid}/download", params={"format": f, "printer_id": "creality_k1"})
        assert r.status_code == 200, (f, r.text)
        assert r.headers["X-Export-Format"] == f and "0.2mm." + f in r.headers["content-disposition"]
    r = c.get(f"/api/export/{bid}/download", params={"format": "stl", "name": 'Lamp <final>?'})
    assert 'filename="Lamp final.stl"' in r.headers["content-disposition"]
    assert c.get(f"/api/export/{bid}/download", params={"format": "step"}).status_code == 422
    # one-tap rename is remembered for every export and for Back up all
    j = c.put(f"/api/export/{bid}/name", json={"name": "Desk lamp: v2.3mf"}).json()
    assert j == {"name": "Desk lamp v2", "custom": True}
    r = c.get(f"/api/export/{bid}/download", params={"format": "obj"})
    assert 'filename="Desk lamp v2.obj"' in r.headers["content-disposition"]
    z = zipfile.ZipFile(io.BytesIO(c.get("/api/me/backup.zip").content))
    assert "Desk lamp v2.3mf" in z.namelist()
    assert c.put(f"/api/export/{bid}/name", json={"name": ""}).json()["custom"] is False
    # someone else cannot rename or export it
    assert client(ADULT).put(f"/api/export/{bid}/name", json={"name": "x"}).status_code == 404


def test_backup_all_zip_has_every_project_and_index():
    c = client(ADULT)
    a, b = photo_build(c), photo_build(c)
    c.put(f"/api/export/{a}/name", json={"name": "Same"}); c.put(f"/api/export/{b}/name", json={"name": "Same"})
    r = c.get("/api/me/backup.zip")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert "ZEIM backup" in r.headers["content-disposition"] and r.headers["X-Backup-Count"] == "2"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()
    assert "Same.3mf" in names and "Same (2).3mf" in names
    idx = json.loads(z.read("ZEIM backup - contents.json"))
    assert len(idx["projects"]) == 2 and all(p["file"] for p in idx["projects"])
    assert z.read("Same.3mf")[:2] == b"PK"
    stl = zipfile.ZipFile(io.BytesIO(c.get("/api/me/backup.zip", params={"format": "stl"}).content))
    assert "Same.stl" in stl.namelist()
    # a guest's backup only holds the guest's own projects
    assert zipfile.ZipFile(io.BytesIO(client().get("/api/me/backup.zip").content)).namelist() == ["ZEIM backup - contents.json"]


def test_resin_output_in_every_format_with_name():
    c = client(ADULT)
    m = trimesh.creation.box(extents=[10, 10, 10])
    r = c.post("/api/resin/prepare", data={"printer_id": "elegoo_saturn4_ultra", "hollow": "false", "supports": "false"},
               files={"file": ("cube.stl", m.export(file_type="stl"), "model/stl")})
    assert r.status_code == 200, r.text
    ex = r.json()["export"]
    assert ex["name"].startswith("cube - ") and ex["name"].endswith(" - 0.05mm")
    for f in ("stl", "3mf", "obj", "ply", "glb", "amf"):
        d = c.get(f"/api/resin/{ex['rid']}/torchc0.{f}")
        assert d.status_code == 200 and f"0.05mm.{f}" in d.headers["content-disposition"]
    d = c.get(f"/api/resin/{ex['rid']}/torchc0.ply", params={"name": "My/print"})
    assert 'filename="My print.ply"' in d.headers["content-disposition"]
    assert client(ADULT).get(f"/api/resin/{ex['rid']}/torchc0.glb").status_code == 404


def test_save_prefs_api():
    g = client()
    assert g.get("/api/me/save-prefs").json() == {"signed_up": False, "prefs": {"mode": "auto", "every": 5}, "stored": False}
    assert g.put("/api/me/save-prefs", json={"mode": "remind", "every": 2}).json()["stored"] == "browser"
    c = client(ADULT)
    for bad in ({"mode": "x"}, {"every": 3}, {"every": "abc"}):
        assert c.put("/api/me/save-prefs", json=bad).status_code == 400
    assert c.put("/api/me/save-prefs", json={"mode": "off", "every": 10}).json()["stored"] == "profile"
    assert c.get("/api/me/save-prefs").json()["prefs"] == {"mode": "off", "every": 10}


def test_ui_wiring():
    idx = (ROOT / "static/index.html").read_text()
    for s in ('id="savePrefs"', 'id="saveWhere"', 'id="backupAll" href="/api/me/backup.zip"', "/static/worksave.js", "/static/exportpick.js"):
        assert s in idx
    cad = (ROOT / "static/cad.html").read_text()
    assert 'id="cwPick"' in cad and "/static/exportpick.js" in cad and "/static/worksave.js" in cad
    js = (ROOT / "static/exportpick.js").read_text()
    assert "zeim.exportfmt." in js and "/api/export/formats" in js
    ws = (ROOT / "static/worksave.js").read_text()
    assert "7 days" in ws and "only in this browser" in ws and "on your account" in ws and "zeim.safariNoteOff" in ws
    assert 'data-export-rid' in (ROOT / "static/torchc0.js").read_text()
