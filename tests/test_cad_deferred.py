"""Deferred CAD items: print-in-place hinges/joints, merge (snap + fuse), Smart merge along recorded
Smart Split cuts, the big-model simplified copy, and the browser checks (1280 / 390)."""
import io

import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient

from app.core import cadjoint, cadops, meshedit
from app.main import app

pytestmark = pytest.mark.skipif(not meshedit.have_boolean(), reason="manifold3d not installed")
c = TestClient(app)


def closed(b):
    mm = b.copy(); mm.merge_vertices(); return mm.is_watertight and mm.volume > 0


@pytest.mark.parametrize("kind,n", [("hinge", 2), ("snap_hinge", 2), ("ball", 2), ("pin", 2), ("chain", 5)])
def test_joint_parts_are_separate_closed_solids_with_a_real_gap(kind, n):
    m, rep = meshedit.apply(trimesh.Trimesh(), "cad_joint", {"kind": kind})
    bs = cadops.bodies(m)
    assert len(bs) == n and all(closed(b) for b in bs)
    assert m.bounds[0][2] == pytest.approx(0, abs=1e-6)                 # sits on the bed
    assert rep["warnings"] and "simulated" in rep["warnings"][0].lower()  # honest, advisory only
    ms = [cadops._to_manifold(b) for b in bs]
    for i in range(n):
        for j in range(i + 1, n):
            assert (ms[i] ^ ms[j]).volume() < 1e-6                     # no overlap
            assert ms[i].min_gap(ms[j], 1.0) >= 0.29                   # at least the 0.3 mm clearance


def test_hinge_pin_is_captured_and_ball_cannot_fall_out():
    (A, B), info = cadjoint.hinge()
    assert info["knuckles"] == 5 and info["clearance_mm"] == 0.3
    (s, k), bi = cadjoint.ball()
    assert bi["opening_mm"] < bi["ball_mm"]                              # opening narrower than the ball


def test_joint_bad_input_is_refused_kindly():
    for p in ({"kind": "blob"}, {"kind": "hinge", "knuckles": 4}, {"kind": "hinge", "length": 10, "knuckles": 9}):
        with pytest.raises(meshedit.OpError):
            meshedit.apply(trimesh.Trimesh(), "cad_joint", p)


def test_joint_api_first_step_label_and_param_filter():
    r = c.post("/api/cad/new", json={"op": "cad_joint", "params": {"kind": "ball", "junk": 1}})
    assert r.status_code == 200, r.text
    ops = c.get(f"/api/edit/{r.json()['id']}").json()["ops"]
    assert ops[0]["label"] == "Add ball joint" and "junk" not in ops[0]["params"]


def _two(gap=20):
    a = trimesh.creation.box([10, 10, 10]); a.apply_translation([0, 0, 5])
    b = trimesh.creation.box([10, 6, 4]); b.apply_translation([gap, 7, 2])
    return cadops._join(a, b)


@pytest.mark.parametrize("snap", ["x+", "x-", "y+", "y-", "z+"])
def test_merge_snaps_then_fuses_into_one_solid(snap):
    m, rep = meshedit.apply(_two(), "merge_bodies", {"bodies": [0, 1], "snap": snap})
    assert len(cadops.bodies(m)) == 1 and closed(m) and not rep["warnings"]
    assert 1240 - 12.5 < m.volume < 1240 - 0.1                          # fused with a small 0.2 mm overlap


def test_merge_apart_warns_but_does_not_block():
    m, rep = meshedit.apply(_two(), "merge_bodies", {"bodies": [0, 1]})
    assert len(cadops.bodies(m)) == 2 and rep["warnings"] and "don't touch" in rep["warnings"][0]
    with pytest.raises(meshedit.OpError):
        meshedit.apply(_two(), "merge_bodies", {"bodies": [0]})


def test_smart_split_records_pieces_and_smart_merge_rejoins_them():
    box = trimesh.creation.box([300, 40, 20]); box.apply_translation([5, 3, 10])
    split, rep = meshedit.apply(box, "smart_split", {})
    pcs = rep["_persist"]["pieces"]
    assert rep["parts"] == len(pcs) >= 2 and len(cadops.bodies(split)) == len(pcs)
    back, r2 = meshedit.apply(split, "smart_merge", {"pieces": pcs})
    assert len(cadops.bodies(back)) == 1 and closed(back)
    assert back.volume == pytest.approx(box.volume, rel=1e-3)
    assert np.allclose(back.bounds, box.bounds - [0, 0, box.bounds[0][2]], atol=0.05) or np.allclose(back.extents, box.extents, atol=0.05)


def test_smart_merge_skips_moved_pieces_kindly():
    box = trimesh.creation.box([300, 40, 20]); box.apply_translation([0, 0, 10])
    split, rep = meshedit.apply(box, "smart_split", {})
    pcs = rep["_persist"]["pieces"]
    bs = cadops.bodies(split); bs[0].apply_translation([0, 0, 50])
    with pytest.raises(meshedit.OpError):                               # only one matches -> nothing to rejoin
        meshedit.apply(cadops._join_all(bs), "smart_merge", {"pieces": pcs})
    with pytest.raises(meshedit.OpError):
        meshedit.apply(split, "smart_merge", {"pieces": []})


def test_smart_split_pieces_are_saved_in_history_for_smart_merge():
    box = trimesh.creation.box([300, 40, 20]); box.apply_translation([0, 0, 10])
    up = c.post("/api/edit/new", files={"file": ("long.stl", io.BytesIO(box.export(file_type="stl")), "model/stl")}).json()
    bid = up.get("id") or up["project"]["id"]
    r = c.post(f"/api/edit/{bid}/op", json={"op": "smart_split", "params": {}}); assert r.status_code == 200, r.text
    pcs = [o for o in r.json()["ops"] if o["op"] == "smart_split"][-1]["params"]["pieces"]
    r = c.post(f"/api/edit/{bid}/op", json={"op": "smart_merge", "params": {"pieces": pcs}}); assert r.status_code == 200, r.text
    assert len(c.get(f"/api/cad/{bid}/scene").json()["bodies"]) == 1


def test_big_model_scene_shows_a_lighter_view_and_keeps_the_full_mesh():
    """Over the CAD face cap: open a display copy. The stored mesh is not rewritten until Simplify."""
    big = trimesh.creation.icosphere(subdivisions=7, radius=30)
    up = c.post("/api/edit/new", files={"file": ("big.stl", io.BytesIO(big.export(file_type="stl")), "model/stl")}).json()
    bid = up.get("id") or up["project"]["id"]
    r = c.get(f"/api/cad/{bid}/scene")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["display_simplified"] is True and d["triangles"] == 327680
    assert 0 < d["display_triangles"] <= 200_000 and d["bodies"]
    assert all(o.get("op") != "simplify" for o in d["ops"])
    keep = round(max(0.02, min(0.98, (200_000 * 0.95) / 327680)), 4)
    r = c.post(f"/api/edit/{bid}/op", json={"op": "simplify", "params": {"keep_ratio": keep}}); assert r.status_code == 200, r.text
    s = c.get(f"/api/cad/{bid}/scene").json()
    assert any(o["op"] == "simplify" for o in s["ops"]) and s["display_triangles"] <= 200_000


def test_deferred_items_in_a_real_browser_1280_390():
    import os
    from test_b4_ui import _run
    os.environ.setdefault("CADD_SHOTS", "/workspace/qa/cadd/shots")
    assert "ALL PASS" in _run("ui_cad_deferred.py")
