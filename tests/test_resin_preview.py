"""TorchC0: a picked model loads into the view right away (POST /api/resin/preview), for STL, ASCII STL, 3MF and OBJ."""
import json
import struct
from pathlib import Path

import pytest
import trimesh

from tests import b1  # noqa: F401
from tests.b1 import ADULT, client

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def c():
    return client(ADULT)


def _faces(body):
    n = struct.unpack_from("<I", body, 80)[0]
    assert 84 + n * 50 == len(body)
    return n


@pytest.mark.parametrize("name,kind", [("cube.stl", "stl"), ("ascii.stl", "stl_ascii"), ("cube.3mf", "3mf"), ("cube.obj", "obj"), ("noext", "stl")])
def test_preview_loads_every_format(c, name, kind):
    m = trimesh.creation.box((20, 20, 20))
    data = m.export(file_type=kind) if kind != "stl_ascii" else trimesh.exchange.stl.export_stl_ascii(m).encode()
    r = c.post("/api/resin/preview", files={"file": (name, data, "application/octet-stream")})
    assert r.status_code == 200, r.text
    assert _faces(r.content) == 12 and r.headers["x-zeim-faces"] == "12"


def test_preview_keeps_every_triangle_unless_simplify_is_asked(c, monkeypatch):
    from app.api import resin as api
    # The simplify cap is re-read in the procjob child, so patching the parent
    # constant alone has no effect (these two tests already failed on zeim).
    monkeypatch.setenv("ZEIM_RESIN_MAX_FACES", "2000")
    monkeypatch.setattr(api, "RESIN_MAX_FACES", 2000)
    m = trimesh.creation.uv_sphere(radius=30, count=[80, 80])
    data = m.export(file_type="3mf")
    r = c.post("/api/resin/preview", files={"file": ("ball.3mf", data, "model/3mf")})
    assert r.status_code == 200, r.text
    assert int(r.headers["x-zeim-faces"]) == len(m.faces) and _faces(r.content) == len(m.faces)
    r = c.post("/api/resin/preview", data={"simplify": "true"}, files={"file": ("ball.3mf", data, "model/3mf")})
    assert r.status_code == 200, r.text
    assert int(r.headers["x-zeim-faces"]) == len(m.faces) and _faces(r.content) < len(m.faces)


def test_preview_rejects_non_models(c):
    assert c.post("/api/resin/preview", files={"file": ("x.stl", b"hello there", "text/plain")}).status_code in (400, 415, 422)
    assert c.post("/api/resin/preview", files={"file": ("x.stl", b"", "model/stl")}).status_code == 400


def test_pick_loads_the_model_into_the_view():
    js = (ROOT / "static/torchc0.js").read_text()
    assert 'id="rzPickView"' in js and '"/api/resin/preview"' in js and "loadPick(f, nm)" in js


def test_big_binary_stl_is_not_refused_for_its_unwelded_vertex_count(c, monkeypatch):
    """Binary STL counts 3 corners per triangle. Those corners are not the vertex cap, so a file
    under the face cap is accepted by the shared check and by TorchC0."""
    from app.services import uploadsafe
    real = uploadsafe.check
    monkeypatch.setattr(uploadsafe, "check", lambda data, **kw: real(data, **{"max_vertices": 900, **kw}))
    data = trimesh.creation.icosphere(2, radius=10).export(file_type="stl")     # 320 faces -> 960 STL corners
    checked = uploadsafe.check(data, max_bytes=1 << 30)
    assert checked.mesh["faces"] == 320 and checked.mesh["vertices"] == 960
    for url in ("/api/resin/preview", "/api/resin/prepare"):
        r = c.post(url, files={"file": ("big.stl", data, "model/stl")})
        assert r.status_code == 200, (url, r.text)


def test_resin_uploads_allow_three_corners_per_face():
    src = (ROOT / "app/api/resin.py").read_text()
    assert "max_vertices=3 * uploadsafe.MAX_FACES" in src


def test_big_binary_stl_keeps_every_triangle_and_prepare_reuses_it(c, monkeypatch):
    """A large binary STL used to be simplified before preview and again before prepare.
    The default path keeps the triangle count. Prepare reuses the loaded copy by id."""
    from app.api import resin as api
    monkeypatch.setenv("ZEIM_RESIN_MAX_FACES", "2000")
    monkeypatch.setattr(api, "RESIN_MAX_FACES", 2000)
    m = trimesh.creation.uv_sphere(radius=20, count=[80, 80])
    m.apply_translation((0, 0, 20))
    data = m.export(file_type="stl")
    r = c.post("/api/resin/preview", files={"file": ("big.stl", data, "model/stl")})
    assert r.status_code == 200, r.text
    assert int(r.headers["x-zeim-faces"]) == len(m.faces) and _faces(r.content) == len(m.faces)
    uid = r.headers["x-zeim-upload"]
    r = c.post("/api/resin/prepare", data={"upload_id": uid, "file_name": "big.stl", "hollow": "false", "supports": "false"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert not any("simplified copy" in n for n in body.get("notes", []))
    assert body.get("triangles_in") == len(m.faces) and body.get("simplified") is False
    r = c.post("/api/resin/prepare", data={"upload_id": uid, "file_name": "big.stl", "hollow": "false", "supports": "false", "simplify": "true"})
    assert r.status_code == 200, r.text
    assert any("simplified copy" in n for n in r.json().get("notes", [])) and r.json().get("simplified") is True


def test_prepare_upload_id_is_checked(c):
    assert c.post("/api/resin/prepare", data={"upload_id": "../../etc"}).status_code == 400
    assert c.post("/api/resin/prepare", data={"upload_id": "0" * 32}).status_code == 410


def test_prepare_waits_for_the_pick_and_sends_its_id():
    js = (ROOT / "static/torchc0.js").read_text()
    assert "await pickLoad" in js and 'fd.append("upload_id", uid)' in js and "X-Zeim-Upload" in js


def test_prepare_progress_names_real_stages(c):
    data = trimesh.creation.box((20, 16, 10)).export(file_type="stl")
    r = c.post("/api/resin/prepare", data={"hollow": "false", "supports": "false", "progress": "true"},
               files={"file": ("box.stl", data, "model/stl")})
    assert r.status_code == 200, r.text
    assert "ndjson" in r.headers["content-type"]
    lines = [json.loads(ln) for ln in r.text.splitlines() if ln.strip()]
    phases = [ln["phase"] for ln in lines]
    assert "orient" in phases and "check" in phases and phases[-1] == "result"
    for ln in lines:
        if ln.get("state") == "start":
            assert "done" not in ln
    result = lines[-1]["result"]
    assert result["preview"]["decimated"] is False
    assert "full prepared mesh" in result["preview"]["note"]
    assert "full resolution" not in result["preview"]["note"].lower()
    assert "preview" not in result["downloads"]
    stl = c.get(result["downloads"]["stl"])
    assert stl.status_code == 200 and _faces(stl.content) >= 12


def test_viewer_preview_is_separate_from_the_full_stl(c, monkeypatch):
    monkeypatch.setenv("ZEIM_RESIN_PREVIEW_FACES", "400")
    mesh = trimesh.creation.uv_sphere(radius=18, count=[36, 36])
    data = mesh.export(file_type="stl")
    r = c.post("/api/resin/prepare", data={"hollow": "false", "supports": "false"},
               files={"file": ("ball.stl", data, "model/stl")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["preview"]["decimated"] is True
    assert "full resolution" not in body["preview"]["note"].lower()
    assert body["preview"]["note"].startswith("Preview only")
    full = c.get(body["downloads"]["stl"]).content
    prev = c.get(body["downloads"]["preview"]).content
    assert _faces(full) > _faces(prev)
    assert _faces(prev) <= 800
