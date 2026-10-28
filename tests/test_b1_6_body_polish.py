"""Body ids and display colours survive a boolean and a repair.

A boolean that leaves the bodies separate used to mint new ids, so a later step that named
the old id failed. A repair that added faces (a filled hole) did the same for that body, and
Check & Repair dropped every id. Colours were stored on the list number, so when the list
changed the colour sat on a different body, or the body came back in the default colour.

These tests fail if a surviving body's id changes, or if its colour is no longer the one
that was saved for it.
"""
import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient

from app.core import cadops, meshedit, stlrepair
from app.main import app
from app.services.history import store

pytestmark = pytest.mark.skipif(not meshedit.have_boolean(), reason="manifold3d not installed")
c = TestClient(app)

RED = {"color": "#cc3344", "finish": "satin"}
BLUE = {"color": "#2244cc", "finish": "gloss"}
GREEN = {"color": "#118844", "finish": "matte"}


def _box(at, size=10):
    mesh = trimesh.creation.box((size, size, size))
    mesh.apply_translation(at)
    return mesh


def _ids(mesh):
    return [(b["id"], round(b["center"][0], 2)) for b in cadops.body_info(mesh)]


def _by_id(mesh):
    return {b["id"]: b for b in cadops.body_info(mesh)}


def test_a_union_that_keeps_both_bodies_keeps_their_ids_for_a_later_step():
    left, right = _box((0, 0, 0)), _box((30, 0, 0))
    both = cadops.ensure_body_ids(cadops._join(left, right))
    info = cadops.body_info(both)
    target, tool = info[0]["id"], info[1]["id"]
    kept, _ = meshedit.apply(both, "body_boolean", {"kind": "union", "target": target, "tool": tool})
    assert _ids(kept) == [(target, 0.0), (tool, 30.0)]
    scaled, _ = meshedit.apply(kept, "body_transform", {"body": tool, "scale": [2, 2, 2]})
    after = _by_id(scaled)
    assert max(after[target]["size"]) == pytest.approx(10, abs=0.05)
    assert max(after[tool]["size"]) == pytest.approx(20, abs=0.15)
    assert after[tool]["center"][0] == pytest.approx(30, abs=0.05)


def test_a_merged_union_keeps_the_target_and_a_bystander_and_its_colour():
    parts = cadops.ensure_body_ids(cadops._join(_box((0, 0, 0)), cadops._join(_box((6, 0, 0)), _box((40, 0, 0)))))
    info = cadops.body_info(parts)
    target, tool, far = (b["id"] for b in info)
    # List numbers, as a project saved before colours were stored on ids.
    pinned = cadops.bind_appearance({"0": RED, "1": BLUE, "2": GREEN}, parts)
    assert set(pinned) == {target, tool, far}
    merged, _ = meshedit.apply(parts, "body_boolean", {"kind": "union", "target": target, "tool": tool})
    assert [b["id"] for b in cadops.body_info(merged)] == [target, far]
    shown = cadops.appearance_for_viewer(pinned, merged)
    # The far body moved from list slot 2 to slot 1. Its colour comes with it.
    # The tool's blue is gone with the tool. The target keeps red.
    assert shown == {"0": RED, "1": GREEN}
    assert shown["1"]["color"] == GREEN["color"]


def test_a_split_subtract_keeps_the_target_id_on_a_piece_and_the_bystander():
    block = trimesh.creation.box((30, 10, 10))
    cutter = trimesh.creation.box((4, 14, 14))
    side = _box((50, 0, 0))
    mesh = cadops.ensure_body_ids(cadops._join(block, cadops._join(side, cutter)))
    info = cadops.body_info(mesh)
    target = next(b["id"] for b in info if b["volume_mm3"] > 2000)
    tool = next(b["id"] for b in info if b["volume_mm3"] < 900)
    side_id = next(b["id"] for b in info if b["center"][0] > 20)
    out, _ = meshedit.apply(mesh, "body_boolean", {"kind": "subtract", "target": target, "tool": tool})
    ids = {b["id"] for b in cadops.body_info(out)}
    assert target in ids and side_id in ids and tool not in ids
    scaled, _ = meshedit.apply(out, "body_transform", {"body": target, "scale": [1, 1, 2]})
    after = _by_id(scaled)
    assert after[target]["size"][2] == pytest.approx(20, abs=0.15)
    assert after[side_id]["size"][2] == pytest.approx(10, abs=0.05)


def test_repair_keeps_ids_so_a_later_step_and_the_colour_still_find_the_body():
    opened = _box((0, 0, 0))
    opened.update_faces(np.arange(len(opened.faces)) != 0)
    holed = cadops.ensure_body_ids(cadops._join(opened, _box((40, 0, 0))))
    info = cadops.body_info(holed)
    left, right = info[0]["id"], info[1]["id"]
    pinned = cadops.bind_appearance({"0": RED, "1": BLUE}, holed)
    fixed, report = meshedit.apply(holed, "repair", {})
    assert report["after"]["watertight"] is True
    assert [b["id"] for b in cadops.body_info(fixed)] == [left, right]
    assert cadops.appearance_for_viewer(pinned, fixed) == {"0": RED, "1": BLUE}
    scaled, _ = meshedit.apply(fixed, "body_transform", {"body": left, "scale": [2, 2, 2]})
    after = _by_id(scaled)
    assert max(after[left]["size"]) == pytest.approx(20, abs=0.15)
    assert max(after[right]["size"]) == pytest.approx(10, abs=0.05)


def test_check_and_repair_keeps_ids_and_colours_when_debris_changes_the_list():
    opened = _box((0, 0, 0))
    opened.update_faces(np.arange(len(opened.faces)) != 0)
    speck = _box((-40, 0, 0), 0.3)
    mix = cadops.ensure_body_ids(cadops._join(speck, cadops._join(opened, _box((40, 0, 0)))))
    info = cadops.body_info(mix)
    assert [round(b["center"][0], 1) for b in info] == [-40.0, 0.0, 40.0]
    speck_id, left, right = (b["id"] for b in info)
    pinned = cadops.bind_appearance({"1": RED, "2": BLUE}, mix)
    fixed, report = stlrepair.repair_mesh(mix)
    assert report["fixed"]["debris_shells_removed"] == 1
    assert report["after"]["watertight"] is True
    assert [b["id"] for b in cadops.body_info(fixed)] == [left, right]
    assert speck_id not in {b["id"] for b in cadops.body_info(fixed)}
    # The red body was list slot 1 and is now slot 0. Blue moves from 2 to 1.
    assert cadops.appearance_for_viewer(pinned, fixed) == {"0": RED, "1": BLUE}


def test_saved_colours_follow_the_body_through_a_boolean_and_undo():
    made = c.post("/api/cad/new", json={"op": "cad_shape", "params": {
        "kind": "box", "dims": {"size": [10, 10, 10]}, "position": [0, 0, 0], "mode": "new"}, "title": "Three"})
    assert made.status_code == 200, made.text
    bid = made.json()["id"]
    for x in (6, 40):
        added = c.post(f"/api/edit/{bid}/op", json={"op": "cad_shape", "params": {
            "kind": "box", "dims": {"size": [10, 10, 10]}, "position": [x, 0, 0], "mode": "new"}})
        assert added.status_code == 200, added.text
    listed = c.get(f"/api/cad/{bid}/bodies").json()
    bodies = listed["bodies"]
    assert [round(b["center"][0], 1) for b in bodies] == [0.0, 6.0, 40.0]
    target, tool, far = (b["id"] for b in bodies)
    # A project from before this polish: colours keyed by list number, not id.
    meta = store.get(bid)
    meta["appearance"] = {"0": RED, "1": BLUE, "2": GREEN}
    store.save(meta)
    merged = c.post(f"/api/edit/{bid}/op", json={"op": "body_boolean", "params": {
        "kind": "union", "target": target, "tool": tool}})
    assert merged.status_code == 200, merged.text
    stored = store.get(bid)["appearance"]
    assert set(stored) == {target, tool, far}
    assert stored[target]["color"] == RED["color"]
    assert stored[far]["color"] == GREEN["color"]
    scene = c.get(f"/api/cad/{bid}/scene").json()
    assert [b["id"] for b in scene["bodies"]] == [target, far]
    assert scene["appearance"] == {"0": RED, "1": GREEN}
    moved = c.post(f"/api/edit/{bid}/op", json={"op": "body_transform", "params": {
        "body": far, "scale": [2, 2, 2]}})
    assert moved.status_code == 200, moved.text
    after = {b["id"]: b for b in c.get(f"/api/cad/{bid}/bodies").json()["bodies"]}
    assert after[far]["center"][0] == pytest.approx(40, abs=0.05)
    assert max(after[far]["size"]) == pytest.approx(20, abs=0.15)
    assert max(after[target]["size"]) == pytest.approx(16, abs=0.2)
    undone = c.post(f"/api/edit/{bid}/undo")
    assert undone.status_code == 200, undone.text
    undone = c.post(f"/api/edit/{bid}/undo")
    assert undone.status_code == 200, undone.text
    back = c.get(f"/api/cad/{bid}/bodies").json()
    far_body = next(b for b in back["bodies"] if b["id"] == far)
    assert far_body["index"] == 2
    assert back["appearance"][str(far_body["index"])]["color"] == GREEN["color"]
    assert back["appearance"]["1"]["color"] == BLUE["color"]
