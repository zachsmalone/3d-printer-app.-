import numpy as np
import trimesh

from app.core import features


def test_box_has_six_planes_and_no_cylinders():
    r = features.detect(trimesh.creation.box((10, 20, 30)))
    assert r["ok"] and r["approximate"]
    assert r["counts"]["planes"] == 6 and r["counts"]["cylinders"] == 0


def test_plate_with_hole_is_detected():
    plate = trimesh.creation.box((40, 40, 10))
    drill = trimesh.creation.cylinder(radius=4, height=30, sections=48)
    m = plate.difference(drill)
    r = features.detect(m)
    assert r["counts"]["holes"] == 1
    h = r["holes"][0]
    assert abs(h["radius"] - 4) < 0.2
    assert abs(abs(h["axis"][2]) - 1) < 0.01


def test_pin_is_a_boss_not_a_hole():
    r = features.detect(trimesh.creation.cylinder(radius=5, height=20, sections=48))
    assert r["counts"]["holes"] == 0
    assert r["cylinders"] and r["cylinders"][0]["role"] == "boss"


def test_empty_and_huge_are_safe():
    assert features.detect(trimesh.Trimesh())["ok"]


def test_smooth_curved_surfaces_are_not_flat():
    assert features.detect(trimesh.creation.icosphere(subdivisions=5))["counts"]["planes"] == 0
    r = features.detect(trimesh.creation.cylinder(radius=5, height=20, sections=1500))
    assert r["counts"]["planes"] == 2          # just the two end caps


def test_result_is_cached_and_payload_capped():
    m = trimesh.creation.box((10, 10, 10))
    for _ in range(6):
        m = m.subdivide()
    a = features.detect(m)
    assert features.detect(m) is a
    assert all(len(p["face_ids"]) <= features.MAX_IDS for p in a["planes"]) and any(p["ids_truncated"] for p in a["planes"])


def test_endpoint_returns_features_for_an_edit_project():
    import io
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    stl = trimesh.creation.box((20, 20, 20)).export(file_type="stl")
    r = c.post("/api/edit/new", files={"file": ("b.stl", io.BytesIO(stl), "model/stl")})
    assert r.status_code == 200, r.text
    bid = r.json()["id"] if "id" in r.json() else r.json()["project"]["id"]
    f = c.get(f"/api/edit/{bid}/features")
    assert f.status_code == 200 and f.json()["counts"]["planes"] == 6 and f.json()["approximate"] is True
    assert c.get("/api/edit/nope/features").status_code in (403, 404)
