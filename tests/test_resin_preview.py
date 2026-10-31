"""TorchC0: a picked model loads into the view right away (POST /api/resin/preview), for STL, ASCII STL, 3MF and OBJ."""
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


def test_preview_simplifies_big_models_for_display(c, monkeypatch):
    from app.api import resin as api
    monkeypatch.setattr(api, "RESIN_MAX_FACES", 2000)
    m = trimesh.creation.uv_sphere(radius=30, count=[80, 80])
    r = c.post("/api/resin/preview", files={"file": ("ball.3mf", m.export(file_type="3mf"), "model/3mf")})
    assert r.status_code == 200, r.text
    assert int(r.headers["x-zeim-faces"]) == len(m.faces) and _faces(r.content) < len(m.faces)


def test_preview_rejects_non_models(c):
    assert c.post("/api/resin/preview", files={"file": ("x.stl", b"hello there", "text/plain")}).status_code in (400, 415, 422)
    assert c.post("/api/resin/preview", files={"file": ("x.stl", b"", "model/stl")}).status_code == 400


def test_pick_loads_the_model_into_the_view():
    js = (ROOT / "static/torchc0.js").read_text()
    assert 'id="rzPickView"' in js and '"/api/resin/preview"' in js and "loadPick(f, nm)" in js


def test_big_binary_stl_is_not_refused_for_its_unwelded_vertex_count(c, monkeypatch):
    """Binary STL counts 3 vertices per triangle: a 2.1M-triangle STL counted 6.3M (> the 3M vertex cap) -> 415 'file type'.
    Shrink the shared vertex default so a small STL hits the same shape of refusal, and check resin still takes it."""
    from app.services import uploadsafe
    real = uploadsafe.check
    monkeypatch.setattr(uploadsafe, "check", lambda data, **kw: real(data, **{"max_vertices": 900, **kw}))
    data = trimesh.creation.icosphere(2, radius=10).export(file_type="stl")     # 320 faces -> 960 STL corners
    with pytest.raises(uploadsafe.Rejected):
        uploadsafe.check(data, max_bytes=1 << 30)                                   # the shared default refuses it
    for url in ("/api/resin/preview", "/api/resin/prepare"):
        r = c.post(url, files={"file": ("big.stl", data, "model/stl")})
        assert r.status_code == 200, (url, r.text)


def test_resin_uploads_allow_three_corners_per_face():
    src = (ROOT / "app/api/resin.py").read_text()
    assert "max_vertices=3 * uploadsafe.MAX_FACES" in src


def test_big_binary_stl_loads_lean_and_prepare_reuses_it_by_id(c, monkeypatch):
    """A 2.1M-triangle STL went through trimesh load + merge + simplify (~1.8 GB) in preview AND again in prepare, next to
    a ~1.3 GB server in a 3 GB container: the kernel killed the child ('busy', then 'too big, turn hollowing off').
    Big binary STLs are now welded + simplified from their bytes, and Prepare reuses preview's copy by id."""
    from app.api import resin as api
    from app.core import meshedit
    monkeypatch.setattr(api, "RESIN_MAX_FACES", 2000)
    real = meshedit.load_mesh
    def no_trimesh(data, ext, *a, **k):
        assert len(data) <= 84 + 50 * 2000, "big binary STL went through the heavy trimesh loader"
        return real(data, ext, *a, **k)
    monkeypatch.setattr(meshedit, "load_mesh", no_trimesh)
    m = trimesh.creation.uv_sphere(radius=20, count=[80, 80])
    m.apply_translation((0, 0, 20))
    data = m.export(file_type="stl")
    r = c.post("/api/resin/preview", files={"file": ("big.stl", data, "model/stl")})
    assert r.status_code == 200, r.text
    assert int(r.headers["x-zeim-faces"]) == len(m.faces) and _faces(r.content) <= 2000
    uid = r.headers["x-zeim-upload"]
    r = c.post("/api/resin/prepare", data={"upload_id": uid, "file_name": "big.stl", "hollow": "false"})
    assert r.status_code == 200, r.text
    assert any("simplified copy" in n for n in r.json().get("notes", [])) and "big" in r.json()["export"]["name"]


def test_prepare_upload_id_is_checked(c):
    assert c.post("/api/resin/prepare", data={"upload_id": "../../etc"}).status_code == 400
    assert c.post("/api/resin/prepare", data={"upload_id": "0" * 32}).status_code == 410


def test_prepare_waits_for_the_pick_and_sends_its_id():
    js = (ROOT / "static/torchc0.js").read_text()
    assert "await pickLoad" in js and 'fd.append("upload_id", uid)' in js and "X-Zeim-Upload" in js
