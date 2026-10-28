"""Hard-surface Measure, fillet/chamfer, and merge paths.

Fillet follows a straight outside edge even when the mesh splits it, and refuses a miss,
an inside corner, or a curved rim it cannot round cleanly. Smart merge keeps a body id.
"""
import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient

from app.core import cadops, meshedit
from app.main import app

pytestmark = pytest.mark.skipif(not meshedit.have_boolean(), reason="manifold3d not installed")
c = TestClient(app)
SQUARE = {"entities": [
    {"id": "a", "type": "line", "p0": [0, 0], "p1": [20, 0]}, {"id": "b", "type": "line", "p0": [20, 0], "p1": [20, 20]},
    {"id": "c", "type": "line", "p0": [20, 20], "p1": [0, 20]}, {"id": "d", "type": "line", "p0": [0, 20], "p1": [0, 0]}],
    "constraints": []}


def _box():
    box = trimesh.creation.box((20, 20, 10))
    box.apply_translation((10, 10, 5))
    return box


def test_a_split_straight_edge_is_rounded_as_one_edge():
    box = _box()
    v, f = trimesh.remesh.subdivide(box.vertices, box.faces)
    sub = trimesh.Trimesh(v, f, process=False)
    half, _ = meshedit.apply(sub, "round_edges", {"radius": 1, "edges": [[[20, 20, 0], [20, 20, 5]]]})
    full, _ = meshedit.apply(sub, "round_edges", {"radius": 1, "edges": [[[20, 20, 0], [20, 20, 10]]]})
    assert half.is_watertight and full.is_watertight
    assert half.volume == pytest.approx(full.volume, abs=0.05)
    assert sub.volume - full.volume > 1


def test_a_slightly_off_pick_rounds_the_same_edge_and_a_miss_is_refused():
    box = _box()
    exact, _ = meshedit.apply(box, "round_edges", {"radius": 1, "edges": [[[20, 20, 0], [20, 20, 10]]]})
    near, _ = meshedit.apply(box, "round_edges", {"radius": 1, "edges": [[[20.3, 20, 0], [20.3, 20, 10]]]})
    assert near.volume == pytest.approx(exact.volume, abs=0.05)
    cadops.ensure_body_ids(box)
    kept = cadops.body_id_of(cadops.bodies(box)[0])
    out, _ = meshedit.apply(box, "round_edges", {"radius": 1, "edges": [[[20, 20, 0], [20, 20, 10]]]})
    assert cadops.body_id_of(cadops.bodies(out)[0]) == kept
    with pytest.raises(meshedit.OpError, match="not on this body"):
        meshedit.apply(box, "round_edges", {"radius": 1, "edges": [[[22, 20, 0], [22, 20, 10]]]})
    other = trimesh.creation.box((10, 10, 10))
    other.apply_translation((40, 0, 5))
    with pytest.raises(meshedit.OpError, match="not on this body"):
        meshedit.apply(cadops._join(box, other), "round_edges", {"body": 0, "radius": 1, "edges": [[[45, 5, 0], [45, 5, 10]]]})


def test_an_inside_corner_is_refused_and_a_curved_rim_is_not_a_speck():
    a = trimesh.creation.box((30, 10, 4))
    a.apply_translation((15, 5, 2))
    b = trimesh.creation.box((10, 10, 16))
    b.apply_translation((5, 5, 8))
    solid, _ = meshedit.apply(cadops._join(a, b), "body_boolean", {"kind": "union", "target": 0, "tool": 1})
    with pytest.raises(meshedit.OpError, match="inside corner"):
        meshedit.apply(solid, "round_edges", {"radius": 1, "edges": [[[10, 0, 4], [10, 10, 4]]]})

    plate, _ = cadops.op_sketch_extrude(trimesh.Trimesh(), {"sketch": {
        "entities": [
            {"id": "a", "type": "line", "p0": [0, 0], "p1": [40, 0]},
            {"id": "b", "type": "line", "p0": [40, 0], "p1": [40, 40]},
            {"id": "c", "type": "line", "p0": [40, 40], "p1": [0, 40]},
            {"id": "d", "type": "line", "p0": [0, 40], "p1": [0, 0]},
        ]}, "distance": 4, "replace": True})
    plate, _ = meshedit.apply(plate, "sketch_extrude", {
        "sketch": {"entities": [{"id": "k", "type": "circle", "c": [20, 20], "r": 6}]},
        "plane": {"origin": [0, 0, 4], "normal": [0, 0, 1]}, "direction": "down", "distance": 4, "mode": "cut"})
    mm = plate.copy()
    mm.merge_vertices()
    seg = None
    for i in np.nonzero(mm.face_adjacency_angles > np.radians(25))[0]:
        ia, ib = mm.face_adjacency_edges[i]
        mid = (mm.vertices[ia] + mm.vertices[ib]) / 2
        if abs(mid[2] - 4) < 0.2 and 5.7 < np.hypot(mid[0] - 20, mid[1] - 20) < 6.3:
            seg = [mm.vertices[ia].tolist(), mm.vertices[ib].tolist()]
            break
    assert seg is not None
    try:
        out, _ = meshedit.apply(plate, "round_edges", {"radius": 0.6, "style": "fillet", "edges": [seg]})
    except meshedit.OpError as e:
        assert "curved" in str(e).lower()
    else:
        assert out.is_watertight and plate.volume - out.volume > 1


def test_smart_merge_keeps_a_split_body_id_and_scene_reports_it():
    box = trimesh.creation.box((300, 40, 20))
    box.apply_translation((5, 3, 10))
    split, rep = meshedit.apply(box, "smart_split", {})
    before = {cadops.body_id_of(b) for b in cadops.bodies(split)}
    back, _ = meshedit.apply(split, "smart_merge", {"pieces": rep["_persist"]["pieces"]})
    assert len(cadops.bodies(back)) == 1
    assert cadops.body_id_of(cadops.bodies(back)[0]) in before

    r = c.post("/api/cad/new", json={"op": "sketch_extrude", "params": {"sketch": SQUARE, "distance": 10}})
    assert r.status_code == 200, r.text
    bid = r.json()["id"]
    scene = c.get(f"/api/cad/{bid}/scene").json()
    listed = c.get(f"/api/cad/{bid}/bodies").json()["bodies"]
    assert scene["bodies"][0]["id"] == listed[0]["id"]
    assert scene["bodies"][0]["id"].startswith("b")
    m = cadops.ensure_body_ids(trimesh.creation.box((10, 10, 10)))
    other = trimesh.creation.box((10, 6, 4))
    other.apply_translation((30, 0, 0))
    joined = cadops._join(m, other)
    cadops.ensure_body_ids(joined)
    parts = cadops.bodies(joined)
    ids = [cadops.public_id(cadops.body_id_of(b)) for b in parts]
    fused, _ = meshedit.apply(joined, "merge_bodies", {"bodies": ids, "snap": "x+"})
    assert len(cadops.bodies(fused)) == 1
    assert cadops.public_id(cadops.body_id_of(cadops.bodies(fused)[0])) == ids[0]
