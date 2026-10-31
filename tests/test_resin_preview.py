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
    monkeypatch.setattr(api, "PREVIEW_FACES", 2000)
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
