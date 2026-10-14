"""Plate editor text tool: raised (emboss) or engraved (deboss) words on one side of ONE selected object, the same
length cap + language / contact filter as every other text, one undoable step."""
import json
import pytest
import trimesh

from app.core import meshedit, plate
from app.services.history import store
from tests.test_comm_features import U, _cube

pytestmark = pytest.mark.skipif(not meshedit.have_boolean(), reason="manifold3d not installed")


def scene():
    a = trimesh.creation.box((40, 30, 20)); a.apply_translation([-30, 0, 10])
    b = trimesh.creation.box((10, 10, 10)); b.apply_translation([30, 0, 5])
    m = trimesh.util.concatenate([a, b])
    _, L = plate.normalise(m, None)
    return m, L


def go(m, L, **p):
    return plate.apply(m, {"layout": L, "action": "text", "sel": [0], "text": "ZEIM", "height": 8, "depth": 1, **p})


def test_raised_text_only_changes_the_selected_object():
    m, L = scene()
    before = plate.objects(m, L)
    m2, rep = go(m, L, mode="emboss", face="top")
    after = plate.objects(m2, rep["layout"])
    assert len(after) == 2 and rep["action"] == "text"
    assert after[0].volume > before[0].volume + 10 and after[0].extents[2] == pytest.approx(21.0, abs=1e-3)
    assert after[1].volume == pytest.approx(before[1].volume) and tuple(after[1].bounds[0]) == pytest.approx(tuple(before[1].bounds[0]))
    assert "Raised text on the top of Object 1" in rep["message"] and "Undo" in rep["message"]
    assert after[0].is_watertight


def test_engraved_text_cuts_in_and_underside_text_stays_on_the_bed():
    m, L = scene()
    v0 = plate.objects(m, L)[0].volume
    m2, rep = go(m, L, mode="deboss", face="front")
    o = plate.objects(m2, rep["layout"])[0]
    assert o.volume < v0 - 10 and o.extents == pytest.approx([40, 30, 20])
    m3, rep3 = go(m, L, mode="emboss", face="bottom")
    o3 = plate.objects(m3, rep3["layout"])[0]
    assert o3.bounds[0][2] == pytest.approx(0, abs=1e-6) and o3.extents[2] == pytest.approx(21.0, abs=1e-3)


def test_needs_one_object_and_explains_text_off_the_side():
    m, L = scene()
    with pytest.raises(plate.PlateError, match="one object"):
        plate.apply(m, {"layout": L, "action": "text", "sel": [0, 1], "text": "A"})
    with pytest.raises(plate.PlateError, match="off this face"):
        go(m, L, offset_u=500)
    with pytest.raises(plate.PlateError, match="1–60"):
        go(m, L, text="")


def test_api_text_is_filtered_never_stored_when_blocked_and_undoable():
    c = U("Pt")
    files = [("files", (f"p{n}.stl", _cube(20), "model/stl")) for n in range(2)]
    bid = c.post("/api/edit/multi", files=files, data={"mode": "plate"}).json()["projects"][0]
    for bad in ("sh1t", "mail me@example.com"):
        r = c.post(f"/api/edit/{bid}/op", json={"op": "plate", "params": {"action": "text", "sel": [0], "text": bad, "mode": "emboss", "face": "top"}})
        assert r.status_code == 422 and r.json()["code"] in ("language_blocked", "contact_blocked"), r.text
        assert bad not in json.dumps(store.get(bid))
    assert c.post(f"/api/edit/{bid}/op", json={"op": "plate", "params": {"action": "text", "sel": [0], "text": "x" * 61}}).status_code == 400
    assert c.post(f"/api/edit/{bid}/op", json={"op": "plate", "params": {"action": "text", "sel": [0], "text": "ok", "font": ["a"]}}).status_code == 400
    r = c.post(f"/api/edit/{bid}/op", json={"op": "plate", "params": {"action": "text", "sel": [0], "text": "HI", "mode": "emboss", "face": "top", "height": 6, "depth": 1}})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["ops"][-1]["label"] == "Plate: Raised text “HI” (1 selected)"
    assert p["plate"]["objects"][0]["size"][2] == pytest.approx(21.0) and p["plate"]["objects"][1]["size"][2] == pytest.approx(20.0)
    p = c.post(f"/api/edit/{bid}/undo").json()
    assert p["plate"]["objects"][0]["size"][2] == pytest.approx(20.0) and len(p["plate"]["objects"]) == 2


def test_replay_skips_a_stored_plate_text_step_that_no_longer_passes_the_filter():
    from app.services import editproj
    assert editproj._replay_safe({"op": "plate", "params": {"action": "text", "text": "sh1t"}}) is False
    assert editproj._replay_safe({"op": "plate", "params": {"action": "text", "text": "Hello"}}) is True
    assert editproj._replay_safe({"op": "plate", "params": {"action": "cut"}}) is True


def test_text_in_a_real_browser():
    from test_b4_ui import _run
    out = _run("ui_plate_text.py")
    assert "PASS webkit" in out, out
