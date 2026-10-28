"""B1-6: a later body step keeps the body it was aimed at when an earlier step moves that body.

Repro: 10 mm box, sphere diameter 10 at x=40, scale ×2 on body 1 (the sphere). Extents are
box 10 and sphere ~20, volume about 5177 mm³. Moving the sphere to x=-40 and replaying used
to scale the box instead (volume about 8522 mm³). The stored reference is now a stable id.
An id that is not on the mesh is an error. A saved index is migrated from the geometry it
named; two bodies with the same centre are refused instead of guessed.
"""
import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient

from app.core import cadops, meshedit
from app.main import app
from app.services import editproj
from app.services.history import store

pytestmark = pytest.mark.skipif(not meshedit.have_boolean(), reason="manifold3d not installed")
c = TestClient(app)

BOX = {"kind": "box", "dims": {"size": [10, 10, 10]}, "position": [0, 0, 0], "mode": "new"}
SPHERE = {"kind": "sphere", "dims": {"diameter": 10}, "position": [40, 0, 0], "mode": "new"}


def _project():
    made = c.post("/api/cad/new", json={"op": "cad_shape", "params": BOX, "title": "Box sphere"})
    assert made.status_code == 200, made.text
    bid = made.json()["id"]
    sphere = c.post(f"/api/edit/{bid}/op", json={"op": "cad_shape", "params": SPHERE})
    assert sphere.status_code == 200, sphere.text
    scaled = c.post(f"/api/edit/{bid}/op", json={"op": "body_transform", "params": {"body": 1, "scale": [2, 2, 2]}})
    assert scaled.status_code == 200, scaled.text
    return bid


def _forget(bid):
    """Drop the warm mesh so the next replay reads the saved file, as a reopened project does."""
    editproj._BASES.pop(bid, None)
    editproj._STATES.pop(bid, None)


def _shells(mesh):
    return sorted(cadops.bodies(mesh), key=lambda b: float(b.bounds.mean(axis=0)[0]))


def _assert_scaled_sphere(mesh):
    """Sphere on the negative side at ×2, box still 10 mm. The old bug scaled the box and left the sphere."""
    parts = _shells(mesh)
    assert len(parts) == 2
    sphere, box = parts
    assert sphere.bounds.mean(axis=0)[0] == pytest.approx(-40, abs=0.05)
    assert max(sphere.extents) == pytest.approx(20, abs=0.15)
    assert max(box.extents) == pytest.approx(10, abs=0.05)
    # 10 mm box is 1000 mm³. A ×2 sphere is about 4177 mm³, together about 5177.
    # Scaling the box instead is about 8522 mm³.
    assert abs(mesh.volume) == pytest.approx(5177, abs=30)


def _move_sphere(bid):
    meta = store.get(bid)
    params = dict(meta["ops"][1]["params"])
    params["position"] = [-40, 0, 0]
    editproj.edit_step(bid, 2, params)


def test_scale_follows_the_sphere_after_it_moves_past_the_box():
    bid = _project()
    mesh = editproj.mesh_at(bid)
    parts = _shells(mesh)
    assert max(parts[0].extents) == pytest.approx(10, abs=0.05)  # box still on the left, unscaled
    assert parts[1].bounds.mean(axis=0)[0] == pytest.approx(40, abs=0.05)
    assert max(parts[1].extents) == pytest.approx(20, abs=0.15)
    stored = store.get(bid)["ops"][2]["params"]["body"]
    assert isinstance(stored, str) and stored.startswith("b")
    assert cadops.body_info(mesh)[1]["id"] == stored
    _forget(bid)
    _move_sphere(bid)
    _forget(bid)
    moved = editproj.mesh_at(bid)
    _assert_scaled_sphere(moved)
    assert store.get(bid)["ops"][2]["params"]["body"] == stored
    assert cadops.body_id_of(_shells(moved)[0]) == int(stored[1:])
    editproj.ensure_exports(bid)
    exported = trimesh.load(store.dir(bid) / "model.stl")
    _assert_scaled_sphere(exported)


def test_legacy_body_index_migrates_and_still_scales_the_sphere():
    bid = _project()
    before = store.get(bid)
    sphere_id = before["ops"][2]["params"]["body"]
    before["ops"][2]["params"]["body"] = 1  # the index this step stored before stable ids
    store.save(before)
    _forget(bid)
    _move_sphere(bid)
    _forget(bid)
    moved = editproj.mesh_at(bid)
    _assert_scaled_sphere(moved)
    assert store.get(bid)["ops"][2]["params"]["body"] == sphere_id


def test_a_missing_body_id_is_an_error_and_does_not_change_the_project():
    bid = _project()
    meta = store.get(bid)
    meta["ops"][2]["params"]["body"] = "b999"
    store.save(meta)
    _forget(bid)
    params = dict(store.get(bid)["ops"][1]["params"])
    params["position"] = [-40, 0, 0]
    with pytest.raises(meshedit.OpError, match="does not match any body"):
        editproj.edit_step(bid, 2, params)
    kept = store.get(bid)
    assert kept["ops"][1]["params"]["position"][0] == 40
    assert kept["ops"][2]["params"]["body"] == "b999"
    with pytest.raises(meshedit.OpError, match="does not match any body"):
        editproj.mesh_at(bid)


def test_a_missing_id_does_not_scale_the_only_remaining_body():
    box, _ = meshedit.apply(trimesh.Trimesh(), "cad_shape", {"kind": "box", "dims": {"size": [10, 10, 10]}, "replace": True})
    verts = box.vertices.copy()
    with pytest.raises(meshedit.OpError, match="does not match any body"):
        meshedit.apply(box, "body_transform", {"body": "b999", "scale": [2, 2, 2]})
    assert np.allclose(box.vertices, verts)
    assert max(box.extents) == pytest.approx(10, abs=1e-6)


def test_a_shared_centre_index_is_refused():
    outer = trimesh.creation.box(extents=(20, 20, 20))
    inner = trimesh.creation.box(extents=(6, 6, 6))
    both = cadops._join(outer, inner)
    cadops.ensure_body_ids(both)
    assert len(cadops.bodies(both)) == 2
    with pytest.raises(meshedit.OpError, match="ambiguous"):
        cadops.bind_legacy_body_refs(both, "body_transform", {"body": 0, "scale": [2, 2, 2]})
    assert max(both.extents) == pytest.approx(20, abs=1e-6)
