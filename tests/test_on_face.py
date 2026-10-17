"""on_face: place a dimensioned shape on a picked face and add or cut it.

The whole point of the feature: an imported mesh becomes editable like native geometry.
The op is anchored to the face's plane (normal + point from the feature detector), never to
triangle ids, so it survives later edits that change the triangulation, and it replays
deterministically through the normal op history with undo/redo.
"""
import io

import numpy as np
import pytest
import trimesh

from app.core import features, meshedit

PLATE_VOLUME = 40.0 * 40.0 * 10.0          # the 40x40x10 test plate


def _plate():
    """A 40x40x10 plate: detectable top plane at z=10 with normal +z."""
    return trimesh.creation.box((40, 40, 10))


def _top_plane(m):
    r = features.detect(m)
    top = max((p for p in r["planes"] if p["normal"][2] > 0.9), key=lambda p: p["origin"][2])
    return {"normal": top["normal"], "point": top["origin"]}


def test_add_cylinder_on_face_grows_the_model():
    m = _plate()
    out, rep = meshedit.op_on_face(m, {"shape": "cylinder", "mode": "add", "plane": _top_plane(m),
                                       "diameter": 6, "height": 5})
    assert out.is_watertight
    added = float(out.volume) - PLATE_VOLUME
    assert abs(added - np.pi * 9 * 5) < 1.0                      # a Ø6x5 boss on top
    assert out.bounds[1][2] > 9.9                               # the boss tops out at z=10 (5+5)
    assert "Added" in rep["message"]


def test_cut_cylinder_on_face_drills_a_hole():
    m = _plate()
    out, _ = meshedit.op_on_face(m, {"shape": "cylinder", "mode": "cut", "plane": _top_plane(m),
                                     "diameter": 6, "height": 8})
    assert out.is_watertight
    removed = PLATE_VOLUME - float(out.volume)
    assert abs(removed - np.pi * 9 * 8) < 1.0                    # a Ø6, 8 mm deep blind hole
    # the hole is visible to the detector as a new hole feature
    assert features.detect(out)["counts"]["holes"] >= 1


def test_cut_through_when_height_exceeds_thickness():
    m = _plate()
    out, _ = meshedit.op_on_face(m, {"shape": "cylinder", "mode": "cut", "plane": _top_plane(m),
                                     "diameter": 6, "height": 20})
    removed = PLATE_VOLUME - float(out.volume)
    assert removed > np.pi * 9 * 10 * 0.9                        # at least a through hole's worth


def test_box_pocket():
    m = _plate()
    out, _ = meshedit.op_on_face(m, {"shape": "box", "mode": "cut", "plane": _top_plane(m),
                                     "width": 10, "depth": 10, "height": 4})
    assert out.is_watertight
    removed = PLATE_VOLUME - float(out.volume)
    assert abs(removed - 10 * 10 * 4) < 40.0                     # a 10x10x4 pocket


def test_off_model_spot_is_refused_not_silent():
    m = _plate()
    with pytest.raises(meshedit.OpError):
        meshedit.op_on_face(m, {"shape": "cylinder", "mode": "add",
                                "plane": {"normal": [0, 0, 1], "point": [500, 500, 10]},
                                "diameter": 6, "height": 5})


def test_bad_params_are_rejected():
    m = _plate()
    with pytest.raises(meshedit.OpError):
        meshedit.op_on_face(m, {"shape": "sphere", "plane": _top_plane(m)})
    with pytest.raises(meshedit.OpError):
        meshedit.op_on_face(m, {"shape": "box", "mode": "chamfer", "plane": _top_plane(m)})
    with pytest.raises(meshedit.OpError):
        meshedit.op_on_face(m, {"shape": "box"})                 # no plane at all


def test_malformed_plane_vectors_are_rejected():
    m = _plate()
    for bad in ("[0, 0]", [0, 0, 1, 0], "not a vector", [float("nan"), 0, 1], [float("inf"), 0, 0]):
        with pytest.raises(meshedit.OpError):
            meshedit.op_on_face(m, {"shape": "cylinder",
                                    "plane": {"normal": bad, "point": [0, 0, 5]}})
    with pytest.raises(meshedit.OpError):
        meshedit.op_on_face(m, {"shape": "cylinder",
                                "plane": {"normal": [0, 0, 1], "point": [0, 0]}})


def test_plane_anchor_survives_retriangulation():
    """The op stores the plane, not triangle ids. Retriangulate the SAME base without changing its
    surface (subdivide: new vertices land on the old faces), confirm the triangulation really
    changed, then apply the same op once to each base and compare the results."""
    m = _plate()
    plane = _top_plane(m)
    r = m.copy(); r = trimesh.Trimesh(vertices=r.vertices, faces=r.faces)
    r = r.subdivide()                                   # 12 -> 48 triangles, same box surface
    assert len(r.faces) > len(m.faces)                  # the triangulation actually changed
    a, _ = meshedit.op_on_face(m, {"shape": "cylinder", "mode": "add", "plane": plane,
                                   "diameter": 6, "height": 5})
    b, _ = meshedit.op_on_face(r, {"shape": "cylinder", "mode": "add", "plane": plane,
                                   "diameter": 6, "height": 5})
    assert abs(float(a.volume) - float(b.volume)) < 1.0   # the same edit lands on both
    assert a.bounds[1][2] > 9.9 and b.bounds[1][2] > 9.9


def test_add_over_a_hole_is_refused_not_detached():
    """A bounding-box check can pass over a hole; the op must refuse a detached addition."""
    m = _plate()
    holed, _ = meshedit.op_on_face(m, {"shape": "cylinder", "mode": "cut", "plane": _top_plane(m),
                                      "diameter": 20, "height": 30})     # a Ø20 through hole in the middle
    assert holed.is_watertight
    with pytest.raises(meshedit.OpError, match="detached"):
        meshedit.op_on_face(holed, {"shape": "cylinder", "mode": "add",
                                    "plane": {"normal": [0, 0, 1], "point": [0, 0, 5]},
                                    "diameter": 6, "height": 5})          # over the hole: nothing to sit on


def test_cut_where_there_is_no_material_is_refused():
    m = _plate()
    holed, _ = meshedit.op_on_face(m, {"shape": "cylinder", "mode": "cut", "plane": _top_plane(m),
                                      "diameter": 20, "height": 30})     # through hole in the middle
    with pytest.raises(meshedit.OpError, match="nothing to cut"):
        meshedit.op_on_face(holed, {"shape": "cylinder", "mode": "cut",
                                    "plane": {"normal": [0, 0, 1], "point": [0, 0, 5]},
                                    "diameter": 6, "height": 8})            # over the same hole


def test_full_flow_through_the_api_with_undo_and_redo():
    """Import -> detect -> pick a face -> add on it -> undo -> redo, through the real endpoints."""
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    stl = _plate().export(file_type="stl")
    r = c.post("/api/edit/new", files={"file": ("p.stl", io.BytesIO(stl), "model/stl")})
    assert r.status_code == 200, r.text
    bid = r.json()["id"] if "id" in r.json() else r.json()["project"]["id"]

    f = c.get(f"/api/edit/{bid}/features").json()
    assert f["counts"]["planes"] == 6
    top = max((p for p in f["planes"] if p["normal"][2] > 0.9), key=lambda p: p["origin"][2])
    plane = {"normal": top["normal"], "point": top["origin"]}

    op = c.post(f"/api/edit/{bid}/op", json={"op": "on_face", "params": {
        "shape": "cylinder", "mode": "add", "plane": plane, "diameter": 6, "height": 5}})
    assert op.status_code == 200, op.text
    with_boss = op.json()["analysis"]["volume_mm3"]

    undo = c.post(f"/api/edit/{bid}/undo")
    assert undo.status_code == 200, undo.text
    after_undo = undo.json()["analysis"]["volume_mm3"]
    redo = c.post(f"/api/edit/{bid}/redo")
    assert redo.status_code == 200, redo.text
    after_redo = redo.json()["analysis"]["volume_mm3"]

    assert abs(after_redo - with_boss) < 0.5                     # redo restores the edit
    assert abs(after_undo - with_boss) > 100.0                   # undo really removed the boss
    assert undo.json()["can_redo"] and not undo.json()["can_undo"]

    # And the edit survives a real export round trip: download the STL, reload it, the boss is there.
    stl = c.get(f"/files/{bid}/model.stl")
    assert stl.status_code == 200 and len(stl.content) > 500
    reloaded = trimesh.load(io.BytesIO(stl.content), file_type="stl")
    assert abs(float(reloaded.volume) - with_boss) < 1.0        # exported mesh keeps the added volume
    assert reloaded.bounds[1][2] > 9.9                         # ...and the boss on top


def test_api_rejects_malformed_plane_vectors():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    stl = _plate().export(file_type="stl")
    r = c.post("/api/edit/new", files={"file": ("p.stl", io.BytesIO(stl), "model/stl")})
    assert r.status_code == 200, r.text
    bid = r.json()["id"] if "id" in r.json() else r.json()["project"]["id"]
    for bad_normal in ("[1, 2]", [1, 2, 3, 4], "zero", ["a", "b", "c"]):
        op = c.post(f"/api/edit/{bid}/op", json={"op": "on_face", "params": {
            "shape": "cylinder", "plane": {"normal": bad_normal, "point": [0, 0, 5]}}})
        assert op.status_code in (400, 422), (bad_normal, op.text)  # clear client error, not a 500
