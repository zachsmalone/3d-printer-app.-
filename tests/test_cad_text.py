"""CAD Text & Emboss tool (op cad_text): raised / cut-in text on a tapped spot or a standalone text plate,
one closed manifold result, advisory (never blocking) print warnings, text filter, exports, real-browser UI."""
import io

import pytest
import trimesh
from fastapi.testclient import TestClient

from app.core import cadops, meshedit
from app.main import app

pytestmark = pytest.mark.skipif(not meshedit.have_boolean(), reason="manifold3d not installed")
c = TestClient(app)


def box():
    b = trimesh.creation.box((40, 30, 20)); b.apply_translation([0, 0, 10]); return b


def solid(m):
    mm = m.copy(); mm.merge_vertices(); return mm.is_watertight and mm.is_winding_consistent and mm.volume > 0


@pytest.mark.parametrize("font", ["sans", "sans-bold", "serif", "mono"])
def test_raised_text_on_top_unions_into_one_body(font):
    b = box()
    m, rep = meshedit.apply(b, "cad_text", {"text": "ZEIM 8", "font": font, "point": [0, 0, 20], "normal": [0, 0, 1], "depth": 1.2})
    assert solid(m) and len(cadops.bodies(m)) == 1 and m.volume > b.volume + 20
    assert m.bounds[1][2] == pytest.approx(21.2, abs=1e-3) and rep["warnings"] == []


def test_cut_text_on_side_face_subtracts_and_stays_inside():
    b = box()
    m, _ = meshedit.apply(b, "cad_text", {"text": "AB", "style": "cut", "point": [0, -15, 10], "normal": [0, -1, 0], "depth": 1, "rotation": 15})
    assert solid(m) and m.volume < b.volume - 10 and (m.bounds == b.bounds).all()


def test_curved_surface_and_misses():
    s = trimesh.creation.icosphere(4, 20)
    m, rep = meshedit.apply(s, "cad_text", {"text": "OK", "size": 10, "point": [0, 0, 20], "normal": [0, 0, 1]})
    assert solid(m) and len(cadops.bodies(m)) == 1
    with pytest.raises(meshedit.OpError, match="Nothing was cut"):
        meshedit.apply(box(), "cad_text", {"text": "X", "style": "cut", "point": [0, 0, 80], "normal": [0, 0, 1]})
    with pytest.raises(meshedit.OpError):
        meshedit.apply(box(), "cad_text", {"text": "X", "font": "comic"})


def test_plate_standalone_and_beside_model():
    m, _ = meshedit.apply(trimesh.Trimesh(), "cad_text", {"text": "Name", "target": "plate", "plate_thickness": 2, "depth": 1})
    assert solid(m) and m.bounds[0][2] == pytest.approx(0) and m.bounds[1][2] == pytest.approx(3)
    m2, _ = meshedit.apply(box(), "cad_text", {"text": "Hi", "target": "plate", "style": "cut", "plate_thickness": 3, "depth": 1})
    assert len(cadops.bodies(m2)) == 2 and solid(m2)
    with pytest.raises(meshedit.OpError, match="less than the plate"):
        meshedit.apply(trimesh.Trimesh(), "cad_text", {"text": "x", "target": "plate", "style": "cut", "plate_thickness": 1, "depth": 1})


def test_fit_is_opt_in_and_makes_text_larger_on_the_face():
    b = box()
    plain, _ = meshedit.apply(b, "cad_text", {"text": "HI", "size": 4, "point": [10, 0, 20], "normal": [0, 0, 1], "depth": 1})
    fitted, rep = meshedit.apply(b, "cad_text", {"text": "HI", "size": 4, "fit": True, "point": [10, 0, 20], "normal": [0, 0, 1], "depth": 1})
    assert solid(fitted) and fitted.volume > plain.volume + 20
    assert "fitted" in rep["message"].lower()


def test_thin_text_warns_but_still_applies():
    m, rep = meshedit.apply(box(), "cad_text", {"text": "tiny", "size": 2, "depth": 0.2, "point": [0, 0, 20], "normal": [0, 0, 1]})
    assert solid(m) and len(rep["warnings"]) == 2 and "nozzle" in rep["warnings"][0]


def test_api_new_plate_then_emboss_undo_export_and_filter():
    j = c.post("/api/cad/new", json={"op": "cad_text", "params": {"text": "ZEIM", "target": "plate"}, "title": "t"})
    assert j.status_code == 200, j.text
    bid = j.json()["id"]
    assert len(j.json()["bodies"]) == 1
    r = c.post(f"/api/edit/{bid}/op", json={"op": "cad_text", "params": {"text": "ab", "size": 2, "depth": 0.2, "point": [0, 0, 3], "normal": [0, 0, 1], "junk": 1}})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["report"]["warnings"] and p["ops"][-1]["op"] == "cad_text" and "junk" not in p["ops"][-1]["params"]
    assert p["ops"][-1]["label"].startswith("Text 'ab'") and p["quality_gate"]["ok"]
    stl = c.get(p["downloads"]["stl"]); assert stl.status_code == 200
    assert trimesh.load(io.BytesIO(stl.content), file_type="stl").is_watertight
    assert c.get(p["downloads"]["3mf"]).status_code == 200
    assert c.post(f"/api/edit/{bid}/undo").status_code == 200
    bad = c.post(f"/api/edit/{bid}/op", json={"op": "cad_text", "params": {"text": "call 555-123-4567", "target": "plate"}})
    assert bad.status_code >= 400
    assert c.post("/api/cad/new", json={"op": "cad_text", "params": {"text": "x" * 61, "target": "plate"}}).status_code >= 400


def test_text_tool_in_a_real_browser_1280_390_320():
    from test_b4_ui import _run
    out = _run("ui_cad_text.py")
    assert "ALL PASS" in out
