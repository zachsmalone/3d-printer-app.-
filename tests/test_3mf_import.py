"""3MF import end to end (Zach, iPhone 2026-10-12: "I can't add 3MF").
iOS hands 3MF files over with odd names/types (x.3mf.zip, no extension, application/zip, model/3mf) and slicer apps write
3MF *Production* packages (the mesh lives in 3D/Objects/*.model, referenced from the root model). All must import, in
Edit and in POST /api/slice. The Edit file input must stay accept-free (iOS greys out unmapped extensions)."""
import io, re, zipfile
from pathlib import Path

import numpy as np, pytest, trimesh
from fastapi.testclient import TestClient

from app.core import meshedit
from app.main import app
from tests.test_slice_api import client, fake_engine  # noqa: F401  (fixtures)

ROOT = Path(__file__).resolve().parents[1]


def plain_3mf():
    return trimesh.creation.box(extents=(20, 30, 10)).export(file_type="3mf")


def production_3mf():
    """Bambu/Orca/Creality-style package: root model only has <components p:path=...>."""
    m = trimesh.creation.box(extents=(10, 10, 10))
    vs = "".join(f'<vertex x="{a}" y="{b}" z="{c}"/>' for a, b, c in m.vertices)
    ts = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in m.faces)
    ns = 'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        z.writestr("3D/Objects/object_1.model", f'<?xml version="1.0"?><model unit="millimeter" {ns}><resources><object id="1" type="model"><mesh><vertices>{vs}</vertices><triangles>{ts}</triangles></mesh></object></resources><build/></model>')
        z.writestr("3D/_rels/3dmodel.model.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/Objects/object_1.model" Id="rel1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        z.writestr("3D/3dmodel.model", f'<?xml version="1.0"?><model unit="millimeter" {ns} xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/1504"><resources><object id="2" type="model"><components><component p:path="/3D/Objects/object_1.model" objectid="1"/></components></object></resources><build><item objectid="2"/></build></model>')
    return buf.getvalue()


@pytest.mark.parametrize("name,mime,want", [
    ("part.3mf", "application/octet-stream", "3mf"), ("part.3MF", "", "3mf"), ("part.gcode.3mf", "", "3mf"),
    ("part.3mf.zip", "application/zip", "3mf"), ("part", "", "3mf"), ("part.zip", "application/zip", "3mf"),
    ("upload", "model/3mf", "3mf"), ("x.bin", "application/vnd.ms-package.3dmanufacturing-3dmodel+xml", "3mf")])
def test_guess_3mf_from_odd_ios_names(name, mime, want):
    assert meshedit.guess_model_ext(name, plain_3mf(), mime) == want


def test_guess_rejects_non_models():
    assert meshedit.guess_model_ext("x.exe", b"MZ" + b"\0" * 200) == ""
    assert meshedit.guess_model_ext("photo.png", b"\x89PNG....") == ""
    assert meshedit.guess_model_ext("a.zip", _zip_without_model()) == ""


def _zip_without_model():
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("readme.txt", "hi")
    return b.getvalue()


def test_production_3mf_loads():
    mesh, _ = meshedit.load_mesh(production_3mf(), "3mf")
    assert np.allclose(mesh.extents, [10, 10, 10])


def _clear(c):
    for b in c.get("/api/builds").json()["builds"]:
        c.delete("/api/builds/" + b["id"])


@pytest.mark.parametrize("name,mime,data", [
    ("part.3mf", "model/3mf", plain_3mf()), ("part.3mf.zip", "application/zip", plain_3mf()),
    ("IMG_noext", "application/octet-stream", plain_3mf()), ("bambu.3mf", "application/octet-stream", production_3mf())])
def test_edit_imports_3mf(name, mime, data):
    c = TestClient(app); _clear(c)
    r = c.post("/api/edit/new", files={"file": (name, data, mime)})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["kind"] == "edit" and j["analysis"]["triangles"] == 12
    assert c.get(j["original"]).content == data
    _clear(c)


def test_edit_rejects_zip_that_is_not_3mf():
    c = TestClient(app)
    assert c.post("/api/edit/new", files={"file": ("a.zip", _zip_without_model(), "application/zip")}).status_code == 415


def test_edit_file_input_and_studio_entry():
    html = (ROOT / "static/index.html").read_text()
    tag = re.search(r'<input[^>]*id="editFile"[^>]*>', html).group(0)
    assert "accept=" not in tag                                  # any file is pickable on iOS; validated by name/type client-side and by content server-side
    assert 'id="btnHave3d"' in html and "3MF" in html
    js = (ROOT / "static/edit.js").read_text()
    assert "3mf" in js and "isModel" in js and "btnHave3d" in js


@pytest.fixture
def sclient(client, fake_engine):
    return client, fake_engine


@pytest.mark.parametrize("name,data", [("m.3mf", plain_3mf()), ("bambu.3mf", production_3mf()), ("m.3mf.zip", plain_3mf())])
def test_slice_accepts_3mf(sclient, name, data):
    c, seen = sclient
    r = c.post("/api/slice", files={"file": (name, data)})
    assert r.status_code == 200, r.text
    assert sorted(r.json()["model_size_mm"]) == sorted([10, 10, 10] if "bambu" in name else [20, 30, 10])


def test_slice_rejects_non_model(sclient):
    c, _ = sclient
    r = c.post("/api/slice", files={"file": ("x.png", b"123")})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_model"
