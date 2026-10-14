"""Plate editor (Slicer tab): several objects on one bed - transform / arrange / merge / separate / group / hide / delete,
undo through the normal step list, and hidden objects left out of the exported + sliced STL."""
import numpy as np
import pytest
import trimesh

from app.core import plate
from tests.test_comm_features import U, _cube


def two():
    a = trimesh.creation.box((10, 10, 10))
    b = trimesh.creation.box((20, 10, 5)); b.apply_translation([30, 0, 2.5])
    return trimesh.util.concatenate([a, b])


def go(m, L, **p):
    return plate.apply(m, {"layout": L, **p})


def test_default_layout_is_connected_components():
    m = two()
    objs, L = plate.normalise(m, None)
    assert len(objs) == 2 and L["hidden"] == [False, False] and sum(L["counts"]) == 24


def test_transform_moves_rotates_and_resizes_only_the_selection():
    m, rep = go(two(), None, action="center", sel=[0, 1])
    m2, rep2 = go(m, rep["layout"], action="transform", sel=[0], x=40, y=-30, rz=90, scale_pct=200)
    d = plate.describe(m2, rep2["layout"])["objects"]
    assert d[0]["center"][:2] == pytest.approx([40, -30], abs=1e-6) and d[0]["size"] == pytest.approx([20, 20, 20], abs=1e-6)
    assert d[0]["min"][2] == pytest.approx(0) and d[1]["size"] == pytest.approx([20, 10, 5])
    m3, rep3 = go(m2, rep2["layout"], action="transform", sel=[1], size_mm={"x": 40})
    assert plate.describe(m3, rep3["layout"])["objects"][1]["size"] == pytest.approx([40, 10, 5])


def test_arrange_is_non_overlapping_and_on_the_bed():
    ms = [trimesh.creation.box((50, 40, 10)) for _ in range(5)]          # all piled on top of each other
    m = trimesh.util.concatenate(ms)
    L = {"counts": [12] * 5, "groups": list(range(5)), "hidden": [False] * 5}
    assert sum("Overlaps" in w for o in plate.describe(m, L)["objects"] for w in o["warnings"]) > 0
    m2, rep = go(m, L, action="arrange", bed=[220, 220, 250])
    d = plate.describe(m2, rep["layout"], (220, 220, 250))
    assert all(not o["warnings"] for o in d["objects"])


def test_arrange_keeps_groups_together_and_group_moves_as_one():
    m, rep = go(two(), None, action="group", sel=[0, 1])
    assert rep["layout"]["groups"] == [0, 0]
    before = plate.describe(m, rep["layout"])["objects"]
    gap = before[1]["min"][0] - before[0]["max"][0]
    m2, rep2 = go(m, rep["layout"], action="arrange")
    after = plate.describe(m2, rep2["layout"])["objects"]
    assert after[1]["min"][0] - after[0]["max"][0] == pytest.approx(gap)
    _, rep3 = go(m2, rep2["layout"], action="ungroup", sel=[0, 1])
    assert len(set(rep3["layout"]["groups"])) == 2


def test_merge_then_separate_round_trip():
    m, rep = go(two(), None, action="merge", sel=[0, 1])
    assert rep["layout"]["counts"] == [len(m.faces)] and "Merged 2" in rep["message"]
    m2, rep2 = go(m, rep["layout"], action="separate", sel=[0])
    assert len(rep2["layout"]["counts"]) == 2
    m3, rep3 = go(m2, rep2["layout"], action="separate", sel=[0])
    assert "Already one piece" in rep3["message"]


def test_duplicate_delete_and_refuse_deleting_everything():
    m, rep = go(two(), None, action="duplicate", sel=[0])
    assert len(rep["layout"]["counts"]) == 3
    m2, rep2 = go(m, rep["layout"], action="delete", sel=[2])
    assert len(rep2["layout"]["counts"]) == 2
    with pytest.raises(plate.PlateError):
        go(m2, rep2["layout"], action="delete", sel=[0, 1])


def test_hidden_objects_are_skipped_by_checks_and_printable_mesh():
    m = two()
    L = {"counts": [12, 12], "groups": [0, 1], "hidden": [False, False]}
    m, rep = go(m, L, action="transform", sel=[1], x=0, y=0)              # now overlapping object 1
    assert any("Overlaps" in w for w in plate.describe(m, rep["layout"])["objects"][0]["warnings"])
    m2, rep2 = go(m, rep["layout"], action="hide", sel=[1])
    d = plate.describe(m2, rep2["layout"])["objects"]
    assert d[0]["warnings"] == [] and d[1]["warnings"] == ["Hidden, won't print."]
    assert len(plate.printable(m2, rep2["layout"]).faces) == 12


def test_api_plate_ops_undo_and_hidden_left_out_of_slice_input():
    from app.api.slice import resolve_model
    from app.community.identity import Actor
    c = U("Pe")
    files = [("files", (f"p{n}.stl", _cube(20), "model/stl")) for n in range(3)]
    j = c.post("/api/edit/multi", files=files, data={"mode": "plate"}).json()
    bid = j["projects"][0]
    p = j["project"]
    assert len(p["plate"]["objects"]) == 3 and len(p["preview"]["bodies"]) == 3
    r = c.post(f"/api/edit/{bid}/op", json={"op": "plate", "params": {"action": "hide", "sel": [2]}})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["plate"]["objects"][2]["hidden"] and p["plate"]["visible"] == 2 and p["ops"][-1]["label"].startswith("Plate: Hide")
    stl = c.get(f"/files/{bid}/model.stl")
    if stl.status_code == 200:
        assert len(trimesh.load(trimesh.util.wrap_as_stream(stl.content), file_type="stl").faces) == 24
    from app.services import editproj
    from app.services.history import store
    editproj.ensure_exports(bid)
    sliced = trimesh.load(str(store.dir(bid) / "model.stl"))            # the file the slicer reads (resolve_model)
    assert len(sliced.faces) == 24
    # a later move keeps the hidden flag; undo brings everything back
    p = c.post(f"/api/edit/{bid}/op", json={"op": "plate", "params": {"action": "transform", "sel": [0], "dx": 5}}).json()
    assert p["plate"]["objects"][2]["hidden"]
    p = c.post(f"/api/edit/{bid}/undo").json(); p = c.post(f"/api/edit/{bid}/undo").json()
    assert not any(o["hidden"] for o in p["plate"]["objects"])
    editproj.ensure_exports(bid)
    assert len(trimesh.load(str(store.dir(bid) / "model.stl")).faces) == 36
    bad = c.post(f"/api/edit/{bid}/op", json={"op": "plate", "params": {"action": "delete", "sel": [0, 1, 2]}})
    assert bad.status_code == 422
