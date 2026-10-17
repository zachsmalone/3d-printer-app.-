import io

import pytest
import trimesh
from fastapi.testclient import TestClient

from app.core import thickness
from app.main import app


def test_thin_plate_is_flagged_and_thick_block_is_ok():
    thin = thickness.analyze(trimesh.creation.box((40, 40, 0.4)), min_wall=0.8)
    assert thin["ok"] and thin["thin_fraction"] > 0.5 and thin["verdict"] == "mostly too thin" and abs(thin["min_found_mm"] - 0.4) < 0.05
    thick = thickness.analyze(trimesh.creation.box((20, 20, 20)), min_wall=0.8)
    assert thick["ok"] and thick["verdict"] == "ok" and thick["thin_points"] == [] and thick["approximate"]


def test_open_empty_and_bad_input_are_refused_cleanly():
    open_mesh = trimesh.creation.box((10, 10, 10)); open_mesh.update_faces(open_mesh.nondegenerate_faces()); open_mesh = trimesh.Trimesh(open_mesh.vertices, open_mesh.faces[:-2])
    assert thickness.analyze(open_mesh)["ok"] is False
    assert thickness.analyze(trimesh.Trimesh())["ok"] is False
    for bad in (0, -1, 1000, float("nan")):
        with pytest.raises(ValueError):
            thickness.analyze(trimesh.creation.box((5, 5, 5)), bad)


def test_endpoint():
    c = TestClient(app)
    stl = trimesh.creation.box((20, 20, 0.5)).export(file_type="stl")
    j = c.post("/api/edit/new", files={"file": ("p.stl", io.BytesIO(stl), "model/stl")}).json()
    bid = j["id"] if "id" in j else j["project"]["id"]
    r = c.get(f"/api/edit/{bid}/thickness?min_wall=0.8")
    assert r.status_code == 200 and r.json()["ok"] and r.json()["verdict"] == "mostly too thin"
    assert c.get(f"/api/edit/{bid}/thickness?min_wall=0").status_code == 400
