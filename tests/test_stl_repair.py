"""Built-in STL / 3MF repair (app/core/stlrepair.py, POST /api/repair, static/repair.html)."""
import io
import zipfile

import numpy as np
import pytest
import trimesh

from tests import b1  # noqa: F401  (isolated PHOTO3D_OUT / DATA before the app is imported)
from tests.b1 import ADULT, client

from app.core import stlrepair


def _stl(m, ascii=False):
    return trimesh.exchange.stl.export_stl_ascii(m).encode() if ascii else trimesh.exchange.stl.export_stl(m)


def _cube(side=20, at=(0, 0, 0)):
    b = trimesh.creation.box((side,) * 3); b.apply_translation(np.add(at, side / 2)); return trimesh.Trimesh(b.vertices, b.faces, process=False)


def _post(c, name, data):
    return c.post("/api/repair", files={"file": (name, io.BytesIO(data), "application/octet-stream")})


@pytest.fixture
def c():   # function scope: runs after conftest resets rate limits (module scope hit the signup limit in the full suite)
    return client(ADULT)


def _load(c, j):
    r = c.get(j["download_url"]); assert r.status_code == 200
    return r.content


def test_holey_flipped_duplicate_degenerate_debris_cube_comes_back_watertight(c):
    m = _cube()
    f = np.delete(m.faces, [0, 1], axis=0)                          # 2 missing triangles: a bent hole (QA B7 shape)
    f[:3] = f[:3, ::-1]                                              # 3 flipped
    f = np.vstack([f, f[3:5], [[0, 0, 1]], [[0, 1, 1]]])            # 2 duplicates + 2 degenerate
    deb = _cube(0.3, (40, 40, 40))                                   # loose 0.3 mm speck
    m = trimesh.Trimesh(np.vstack([m.vertices, deb.vertices]), np.vstack([f, deb.faces + len(m.vertices)]), process=False)
    r = _post(c, "broken.stl", _stl(m)); assert r.status_code == 200, r.text
    j = r.json()
    assert j["before"]["watertight"] is False and j["after"]["watertight"] is True
    x = j["fixed"]
    assert x["duplicate_triangles"] == 2 and x["degenerate_triangles"] == 2 and x["debris_shells_removed"] == 1
    assert x["flipped_triangles_reoriented"] == 3 and x["hole_edges_closed"] >= 4
    assert j["after"]["triangles"] == 12 and j["before"]["triangles"] == len(m.faces)
    out = trimesh.load(io.BytesIO(_load(c, j)), file_type="stl")
    assert out.is_watertight and out.volume == pytest.approx(8000, rel=0.01)
    assert j["filename"] == "broken_repaired.stl"


def test_multibody_part_is_kept_and_ascii_stl_works(c):
    a, b = _cube(), _cube(10, (30, 0, 0))
    m = trimesh.util.concatenate([a, b])
    j = _post(c, "two.stl", _stl(m, ascii=True)).json()
    assert j["after"]["shells"] == 2 and j["fixed"]["debris_shells_removed"] == 0
    assert j["after"]["volume_mm3"] == pytest.approx(9000, rel=1e-6)


def test_inverted_binary_stl_is_turned_outward(c):
    m = _cube(); m.invert()
    j = _post(c, "inv.stl", _stl(m)).json()
    assert j["before"]["inverted"] is True and j["after"]["inverted"] is False and j["fixed"]["flipped_triangles_reoriented"] == 12
    assert trimesh.load(io.BytesIO(_load(c, j)), file_type="stl").volume == pytest.approx(8000)


def test_3mf_round_trip(c):
    m = _cube(); f = np.delete(m.faces, [4], axis=0)
    data = trimesh.Trimesh(m.vertices, f, process=False).export(file_type="3mf")
    r = _post(c, "part.3mf", data); assert r.status_code == 200, r.text
    j = r.json(); assert j["format"] == "3mf" and j["after"]["watertight"]
    blob = _load(c, j); assert zipfile.is_zipfile(io.BytesIO(blob))
    out = trimesh.load(io.BytesIO(blob), file_type="3mf", force="mesh")
    assert out.is_watertight and abs(out.volume) == pytest.approx(8000, rel=1e-6)


def test_download_is_private_to_the_uploader(c):
    j = _post(c, "a.stl", _stl(_cube())).json()
    other = client(ADULT); other.cookies.clear()
    assert other.get(j["download_url"]).status_code == 404
    assert c.get("/api/repair/zzzz").status_code == 404


@pytest.mark.parametrize("name,data,code", [
    ("empty.stl", b"", 400), ("junk.stl", b"\x00\x01garbage" * 50, 415), ("photo.jpg", b"\xff\xd8\xff" + b"0" * 200, 415),
    ("notes.txt", b"hello world", 415), ("cut.stl", _stl(_cube())[:150], 415),
    ("flat.stl", trimesh.exchange.stl.export_stl(trimesh.Trimesh([[0, 0, 0], [1, 0, 0], [2, 0, 0]], [[0, 1, 2]], process=False)), 422)])
def test_bad_input_is_a_friendly_4xx(c, name, data, code):
    r = _post(c, name, data)
    assert r.status_code == code, (r.status_code, r.text)
    assert isinstance(r.json()["detail"], str) and r.json()["detail"]


def test_no_file_is_400(c):
    assert c.post("/api/repair").status_code in (400, 422)


def test_large_file_is_handled_or_refused_cleanly(c):
    s = trimesh.creation.icosphere(subdivisions=7, radius=30)        # 327 680 faces (~16 MB binary STL)
    f = s.faces[s.triangles_center[:, 2] < 29.5]                       # with a hole at the top
    r = _post(c, "big.stl", _stl(trimesh.Trimesh(s.vertices, f, process=False)))
    assert r.status_code in (200, 422), r.text
    if r.status_code == 200:
        assert r.json()["after"]["watertight"] and r.json()["before"]["triangles"] == len(f)


def test_core_function_reports_unfixable_nonmanifold(c):
    a, b = _cube(), _cube(at=(20, 20, 0))                              # two cubes sharing one vertical edge
    out, rep = stlrepair.repair_mesh(trimesh.util.concatenate([a, b]))
    assert rep["after"]["triangles"] == 24 and set(rep["fixed"]) >= {"hole_edges_closed", "nonmanifold_edges_fixed"}


def test_repair_page_is_linked_from_import_and_mobile_friendly():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1] / "static"
    assert 'href="/static/repair.html"' in (root / "index.html").read_text(encoding="utf-8")
    html = (root / "repair.html").read_text(encoding="utf-8")
    assert 'name="viewport"' in html and 'id="rpFile"' in html and "/static/repair.js" in html and "<script>" not in html.split("</head>")[1]
    assert "min-height:48px" in (root / "style.css").read_text(encoding="utf-8")
