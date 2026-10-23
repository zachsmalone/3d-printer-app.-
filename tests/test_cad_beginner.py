"""Beginner shapes (op cad_shape: new / join / cut, reusing the parts-builder primitives) + lessons UI in a real browser."""
import pytest
import trimesh
from fastapi.testclient import TestClient

from app.core import cadops, meshedit
from app.main import app

pytestmark = pytest.mark.skipif(not meshedit.have_boolean(), reason="manifold3d not installed")
c = TestClient(app)


def solid(m):
    mm = m.copy(); mm.merge_vertices(); return mm.is_watertight and mm.is_winding_consistent and mm.volume > 0


def first(kind="box", **kw):
    return meshedit.apply(trimesh.Trimesh(), "cad_shape", {"kind": kind, "replace": True, **kw})[0]


@pytest.mark.parametrize("kind", ["box", "cylinder", "sphere", "cone", "torus", "tube", "wedge"])
def test_every_shape_is_a_solid_resting_on_the_bed(kind):
    m = first(kind, position=[5, -3, 0])
    assert solid(m) and m.bounds[0][2] == pytest.approx(0, abs=1e-6)
    assert (m.bounds[0][:2] + m.bounds[1][:2]) / 2 == pytest.approx([5, -3], abs=1e-6)


def test_wedge_is_half_a_box():
    assert first("wedge", dims={"size": [20, 10, 10]}).volume == pytest.approx(1000, rel=1e-6)


def test_new_join_cut():
    b = first(dims={"size": [20, 20, 10]})
    two, _ = meshedit.apply(b, "cad_shape", {"kind": "sphere", "position": [40, 0, 0]})
    assert len(cadops.bodies(two)) == 2
    j, _ = meshedit.apply(b, "cad_shape", {"kind": "cylinder", "mode": "join", "position": [0, 0, 9.5]})
    assert solid(j) and len(cadops.bodies(j)) == 1 and j.bounds[1][2] > 25
    h, rep = meshedit.apply(b, "cad_shape", {"kind": "cylinder", "mode": "cut", "dims": {"diameter": 5, "height": 12}, "position": [0, 0, -1]})
    assert solid(h) and h.volume < b.volume - 150 and "hole" in rep["message"]
    with pytest.raises(meshedit.OpError):
        meshedit.apply(b, "cad_shape", {"kind": "torus", "dims": {"outer": 10, "tube": 6}})   # self-intersecting ring refused
    with pytest.raises(meshedit.OpError):
        meshedit.apply(b, "cad_shape", {"kind": "blob"})


def test_api_first_step_history_label_and_param_filter():
    r = c.post("/api/cad/new", json={"op": "cad_shape", "params": {"kind": "cylinder", "dims": {"diameter": 40, "height": 4}, "junk": 1}})
    assert r.status_code == 200, r.text
    bid = r.json()["id"]
    r = c.post(f"/api/edit/{bid}/op", json={"op": "cad_shape", "params": {"kind": "cylinder", "mode": "cut", "dims": {"diameter": 5, "height": 6}, "position": [14, 0, -1]}})
    assert r.status_code == 200, r.text
    ops = r.json()["ops"]
    assert [o["label"] for o in ops] == ["Cylinder", "Cylinder hole"] and "junk" not in ops[0]["params"]
    assert c.get(f"/api/download/{bid}/stl").status_code == 200


def test_beginner_shapes_and_lessons_in_a_real_browser_1280_390_320():
    from test_b4_ui import _run
    assert "ALL PASS" in _run("ui_cad_beginner.py")
