"""Plate editor cut tool: cut ONE selected object with a flat plane across X / Y / Z, optional Smart Split connector
(magnet / dovetail / pin / glue, sizes from data/split/split-specs.json), fit labelled Simulated, one undoable step."""
import numpy as np
import pytest
import trimesh

from app.core import meshedit, plate, smartsplit
from tests.test_comm_features import U, _cube

needs_bool = pytest.mark.skipif(not meshedit.have_boolean(), reason="manifold3d not installed")


def scene():
    a = trimesh.creation.box((40, 30, 30)); a.apply_translation([30, 20, 15])     # off-centre on purpose
    b = trimesh.creation.box((10, 10, 10)); b.apply_translation([-60, 0, 5])
    m = trimesh.util.concatenate([a, b])
    _, L = plate.normalise(m, None)
    big = [i for i, o in enumerate(plate.objects(m, L)) if o.extents[0] > 20][0]
    return m, L, big


def cut(m, L, **p):
    return plate.apply(m, {"layout": L, "action": "cut", **p})


def test_plain_cut_makes_two_pieces_in_place_of_the_object_and_keeps_the_rest():
    m, L, i = scene()
    m2, rep = cut(m, L, sel=[i], axis="z", offset=12)
    d = plate.describe(m2, rep["layout"])["objects"]
    assert len(d) == 3 and rep["action"] == "cut"
    sizes = sorted(tuple(o["size"]) for o in d)
    assert (10.0, 10.0, 10.0) in sizes and (40.0, 30.0, 12.0) in sizes and (40.0, 30.0, 18.0) in sizes
    assert all(o["min"][2] == pytest.approx(0, abs=1e-6) for o in d)              # every piece sits on the bed
    assert not any(w for o in d for w in o["warnings"]), d                          # second piece placed on the bed, no overlaps
    assert rep["cut"]["verification"] == "Simulated" and "Simulated" in rep["message"] and "Undo" in rep["message"]
    assert rep["cut"]["watertight"] == [True, True]
    assert len(set(rep["layout"]["groups"])) == 3                                   # pieces are separate objects
    vol = sum(o.volume for o in plate.objects(m2, rep["layout"]))
    assert vol == pytest.approx(m.volume, rel=1e-6)


@pytest.mark.parametrize("axis,exp", [("x", (12.0, 30.0, 30.0)), ("y", (40.0, 12.0, 30.0))])
def test_side_cuts_stand_by_default_and_can_lay_on_the_cut_face(axis, exp):
    m, L, i = scene()
    m2, rep = cut(m, L, sel=[i], axis=axis, offset=12)
    assert tuple(plate.describe(m2, rep["layout"])["objects"][i]["size"]) == exp
    m3, rep3 = cut(m, L, sel=[i], axis=axis, offset=12, lay_flat=True)
    sz = plate.describe(m3, rep3["layout"])["objects"][i]["size"]
    assert sz[2] == pytest.approx(12.0) and rep3["cut"]["laid_on_cut_face"] == [0, 1]


@needs_bool
@pytest.mark.parametrize("join", ["magnet", "pin", "dovetail", "glue"])
def test_connectors_reuse_split_specs_and_stay_watertight(join):
    m, L, i = scene()
    m2, rep = cut(m, L, sel=[i], axis="z", offset=12, join=join, material="PETG")
    c = rep["cut"]
    assert c["join"] == join and c["verification"] == "Simulated" and c["watertight"] == [True, True]
    assert "Simulated" in c["note"] and "test piece" in c["note"]
    sp = smartsplit.specs()
    if join == "dovetail":
        assert c["connector"]["clearance_mm"] == sp["dovetails"]["starting_geometry"]["per_side_clearance_mm"]["PETG"]
        assert c["connector"]["depth_mm"] == sp["dovetails"]["starting_geometry"]["depth_mm"]
    if join == "pin":
        assert c["connector"]["clearance_mm"] == sp["alignment_pins"]["starting_geometry"]["hole_clearance_mm"]["PETG"]
        assert c["connector"]["pin_diameter_mm"] == sp["alignment_pins"]["starting_geometry"]["pin_diameter_mm"]
    if join == "magnet":
        assert c["connector"]["clearance_mm"] == 0.30 and c["connector"]["pockets"] == 2
    pieces = plate.objects(m2, rep["layout"])
    assert len(pieces) == 3 and all(p.is_watertight for p in pieces)


@needs_bool
def test_magnet_pockets_are_on_both_cut_faces_with_the_spec_gap():
    m, L, i = scene()
    m2, rep = cut(m, L, sel=[i], axis="z", offset=12, join="magnet", magnet_diameter=6, magnet_thickness=3, count=2)
    a, b = [p for p in plate.objects(m2, rep["layout"]) if p.extents[0] > 20]
    pocket = 2 * plate._cyl_vol((6 + 0.25) / 2, 3 + 0.15)
    assert a.volume == pytest.approx(40 * 30 * 12 - pocket, rel=1e-3)
    assert b.volume == pytest.approx(40 * 30 * 18 - pocket, rel=1e-3)


@needs_bool
def test_dovetail_is_centred_on_an_off_centre_cut_face():
    """Regression: the tab used to sit on the world axis, not on the cut face (a model away from (0, 0) lost it)."""
    m, L, i = scene()
    _, rep = cut(m, L, sel=[i], axis="z", offset=12, join="dovetail")
    at = rep["cut"]["connector"]["at"][0]
    assert at[0] == pytest.approx(30, abs=0.5) and at[1] == pytest.approx(20, abs=0.5) and at[2] == pytest.approx(12)


@needs_bool
@pytest.mark.parametrize("join", ["magnet", "dovetail"])
def test_connector_that_would_break_through_is_refused_with_plain_words(join):
    t = trimesh.creation.box((60, 8, 20)); t.apply_translation([0, 0, 10])           # 8 mm thin wall
    _, L = plate.normalise(t, None)
    with pytest.raises(plate.PlateError, match="not fit inside this cut face"):
        cut(t, L, sel=[0], axis="x", offset=30, join=join)
    with pytest.raises(plate.PlateError, match="not fit"):
        cut(t, L, sel=[0], axis="z", offset=2, join="magnet")


def test_bad_requests_are_refused_and_change_nothing():
    m, L, i = scene()
    with pytest.raises(plate.PlateError, match="one object"):
        cut(m, L, sel=[0, 1], axis="z", offset=5)
    with pytest.raises(plate.PlateError, match="inside the object"):
        cut(m, L, sel=[i], axis="z", offset=40)
    with pytest.raises(plate.PlateError, match="X, Y or Z"):
        cut(m, L, sel=[i], axis="q", offset=5)
    with pytest.raises(plate.PlateError, match="Join must be"):
        cut(m, L, sel=[i], axis="z", offset=5, join="screws")
    with pytest.raises(plate.PlateError, match="PLA or PETG"):
        cut(m, L, sel=[i], axis="z", offset=5, join="pin", material="ABS")


def test_hidden_object_stays_hidden_after_cut_and_label_names_the_step():
    m, L, i = scene()
    m1, r1 = plate.apply(m, {"layout": L, "action": "hide", "sel": [i]})
    m2, r2 = cut(m1, r1["layout"], sel=[i], axis="z", offset=10)
    assert r2["layout"]["hidden"][i] and r2["layout"]["hidden"][i + 1]
    assert plate.label({"action": "cut", "sel": [i], "axis": "z", "offset": 10, "join": "magnet"}) == "Plate: Cut Z at 10 mm (magnet)"


def test_api_cut_is_one_undoable_step_and_redo_brings_it_back():
    c = U("Pc")
    files = [("files", (f"p{n}.stl", _cube(20), "model/stl")) for n in range(2)]
    j = c.post("/api/edit/multi", files=files, data={"mode": "plate"}).json()
    bid = j["projects"][0]
    r = c.post(f"/api/edit/{bid}/op", json={"op": "plate", "params": {"action": "cut", "sel": [0], "axis": "z", "offset": 8, "join": "none"}})
    assert r.status_code == 200, r.text
    p = r.json()
    assert len(p["plate"]["objects"]) == 3 and len(p["preview"]["bodies"]) == 3
    assert p["ops"][-1]["label"] == "Plate: Cut Z at 8 mm"
    assert p["report"]["cut"]["verification"] == "Simulated"
    sizes = sorted(o["size"][2] for o in p["plate"]["objects"])
    assert sizes == pytest.approx([8, 12, 20])
    p = c.post(f"/api/edit/{bid}/undo").json()
    assert len(p["plate"]["objects"]) == 2
    p = c.post(f"/api/edit/{bid}/redo").json()
    assert len(p["plate"]["objects"]) == 3
    bad = c.post(f"/api/edit/{bid}/op", json={"op": "plate", "params": {"action": "cut", "sel": [0], "axis": "z", "offset": 999}})
    assert bad.status_code == 422 and "inside the object" in bad.text
    assert len(c.get(f"/api/edit/{bid}").json()["plate"]["objects"]) == 3


def test_cut_tool_is_in_the_plate_editor_ui():
    js = open("static/plate.js", encoding="utf-8").read()
    assert 'data-plate="cut"' in js and "Simulated" in js and "Undo puts the object back" in js
    for j in ("magnet", "dovetail", "pin", "glue"):
        assert f'["{j}"' in js


def test_cut_in_a_real_browser():
    from test_b4_ui import _run
    out = _run("ui_plate_cut.py")
    assert "PASS webkit" in out, out
