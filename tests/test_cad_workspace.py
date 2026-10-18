"""CAD workspace: sketch solver, regions, solid ops as history steps, replay, rename, appearance."""
import math

import pytest
import trimesh
from fastapi.testclient import TestClient

from app.core import cadops, sketch
from app.main import app

c = TestClient(app)
SQUARE = {"entities": [
    {"id": "a", "type": "line", "p0": [0, 0], "p1": [20, 0]}, {"id": "b", "type": "line", "p0": [20, 0], "p1": [20, 20]},
    {"id": "c", "type": "line", "p0": [20, 20], "p1": [0, 20]}, {"id": "d", "type": "line", "p0": [0, 20], "p1": [0, 0]}],
    "constraints": []}


def test_solver_lines_dimensions_and_constraints():
    s = {"entities": [{"id": "a", "type": "line", "p0": [0, 0], "p1": [10, 1]}, {"id": "b", "type": "line", "p0": [10, 1], "p1": [9, 8]},
                      {"id": "k", "type": "circle", "c": [3, 3], "r": 1}],
         "constraints": [{"type": "lock", "a": "a.p0"}, {"type": "horizontal", "a": "a"}, {"type": "coincident", "a": "a.p1", "b": "b.p0"},
                         {"type": "perpendicular", "a": "a", "b": "b"}, {"type": "length", "a": "a", "value": 20},
                         {"type": "radius", "a": "k", "value": 2.5}, {"type": "tangent", "a": "a", "b": "k"}]}
    r = sketch.solve(s)
    assert r["ok"]
    e = {x["id"]: x for x in r["sketch"]["entities"]}
    assert e["a"]["p0"] == pytest.approx([0, 0], abs=1e-6) and e["a"]["p1"] == pytest.approx([20, 0], abs=1e-6)
    assert e["b"]["p1"][0] == pytest.approx(20, abs=1e-5)
    assert e["k"]["r"] == pytest.approx(2.5) and abs(e["k"]["c"][1]) == pytest.approx(2.5, abs=1e-5)


def test_solver_equal_parallel_concentric_angle():
    s = {"entities": [{"id": "a", "type": "line", "p0": [0, 0], "p1": [10, 0]}, {"id": "b", "type": "line", "p0": [0, 5], "p1": [7, 7]},
                      {"id": "p", "type": "circle", "c": [0, 0], "r": 3}, {"id": "q", "type": "circle", "c": [1, 1], "r": 5}],
         "constraints": [{"type": "lock", "a": "a.p0"}, {"type": "lock", "a": "a.p1"}, {"type": "parallel", "a": "a", "b": "b"},
                         {"type": "equal", "a": "a", "b": "b"}, {"type": "concentric", "a": "p", "b": "q"}]}
    r = sketch.solve(s)
    assert r["ok"]
    e = {x["id"]: x for x in r["sketch"]["entities"]}
    v = [e["b"]["p1"][i] - e["b"]["p0"][i] for i in (0, 1)]
    assert math.hypot(*v) == pytest.approx(10, abs=1e-5) and abs(v[1]) < 1e-5
    assert e["p"]["c"] == pytest.approx(e["q"]["c"], abs=1e-6)
    s2 = {"entities": s["entities"][:2], "constraints": [{"type": "lock", "a": "a.p0"}, {"type": "lock", "a": "a.p1"}, {"type": "angle", "a": "a", "b": "b", "value": 30}]}
    e2 = {x["id"]: x for x in sketch.solve(s2)["sketch"]["entities"]}
    d = [e2["b"]["p1"][i] - e2["b"]["p0"][i] for i in (0, 1)]
    assert abs(math.degrees(math.atan2(d[1], d[0]))) == pytest.approx(30, abs=1e-3)


def test_regions_even_odd_pick_trim_offset():
    s = sketch.check({"entities": [*SQUARE["entities"], {"id": "h", "type": "circle", "c": [10, 10], "r": 3}]})
    r = sketch.region_rings(s)
    assert len(r) == 1 and len(r[0]["holes"]) == 1 and r[0]["area"] == pytest.approx(400 - math.pi * 9, rel=1e-2)
    assert sketch.region_rings(s, [[10, 10]])[0]["area"] == pytest.approx(math.pi * 9, rel=1e-2)
    assert [e["type"] for e in sketch.trim(s, "a", [10, 0])] == []  # whole edge (no crossings) goes
    t = sketch.trim(sketch.check({"entities": [{"id": "l", "type": "line", "p0": [-20, 0], "p1": [20, 0]}, {"id": "k", "type": "circle", "c": [0, 0], "r": 5}]}), "l", [0, 0])
    assert len(t) == 2 and t[0]["p1"] == pytest.approx([-5, 0], abs=0.05)
    assert sketch.offset(s, "h", 2)["r"] == 5
    with pytest.raises(sketch.SketchError):
        sketch.check({"entities": [{"type": "blob"}]})


def test_kernel_ops_are_solid():
    e = trimesh.Trimesh()
    m, _ = cadops.op_sketch_extrude(e, {"sketch": SQUARE, "distance": 10, "replace": True})
    assert m.is_watertight and m.volume == pytest.approx(4000, rel=1e-6)
    cut, _ = cadops.op_sketch_extrude(m, {"sketch": {"entities": [{"id": "k", "type": "circle", "c": [10, 10], "r": 4}]},
                                          "plane": {"origin": [0, 0, 10], "normal": [0, 0, 1]}, "direction": "down", "distance": 10, "mode": "cut"})
    assert cut.volume == pytest.approx(4000 - math.pi * 160, rel=1e-2)
    both, _ = cadops.op_sketch_extrude(e, {"sketch": SQUARE, "distance": 10, "direction": "both", "replace": True})
    assert both.bounds[0][2] == pytest.approx(-5)
    rv, _ = cadops.op_revolve(e, {"sketch": {"entities": [{"id": "r", "type": "polygon", "c": [15, 0], "r": 2, "n": 4}]}, "plane": "XZ", "replace": True})
    assert rv.is_watertight and rv.bounds[1][0] == pytest.approx(17, abs=0.1)
    with pytest.raises(Exception):
        cadops.op_revolve(e, {"sketch": SQUARE, "axis": {"p": [10, 0], "d": [0, 1]}, "replace": True})
    fo, _ = cadops.op_face_offset(m, {"point": [5, 5, 10], "normal": [0, 0, 1], "distance": 5})
    assert fo.bounds[1][2] == pytest.approx(15) and fo.volume == pytest.approx(6000, rel=1e-6)
    ch, _ = cadops.op_round_edges(m, {"radius": 1, "style": "chamfer"})
    assert ch.is_watertight and ch.volume < m.volume
    pat, _ = cadops.op_pattern(m, {"kind": "linear", "count": 3, "step": [30, 0, 0]})
    assert len(cadops.bodies(pat)) == 3
    circ, _ = cadops.op_pattern(m, {"kind": "circular", "count": 4, "center": [60, 0, 0]})
    assert len(cadops.bodies(circ)) == 4
    al, _ = cadops.op_align(pat, {"body": 2, "axis": "z", "side": "min", "value": 7})
    assert cadops.bodies(al)[2].bounds[0][2] == pytest.approx(7)
    two = cadops._join(m, cadops.op_body_transform(m, {"move": [10, 0, 0]})[0])
    u, _ = cadops.op_body_boolean(two, {"kind": "union", "target": 0, "tool": 1})
    assert len(cadops.bodies(u)) == 1 and u.volume == pytest.approx(6000, rel=1e-6)
    s, _ = cadops.op_body_boolean(two, {"kind": "subtract", "target": 0, "tool": 1})
    assert s.volume == pytest.approx(2000, rel=1e-6)
    mir, _ = cadops.op_body_transform(m, {"mirror": "x", "copy": True, "pivot": [30, 0, 0]})
    assert len(cadops.bodies(mir)) == 2 and mir.is_watertight
    sc, _ = cadops.op_body_transform(m, {"scale": [2, 1, 1]})
    assert sc.volume == pytest.approx(8000, rel=1e-6)


def test_fillet_selected_edge_only():
    m, _ = cadops.op_sketch_extrude(trimesh.Trimesh(), {"sketch": SQUARE, "distance": 10, "replace": True})
    one, _ = cadops.op_round_edges(m, {"radius": 2, "edges": [[[20, 20, 0], [20, 20, 10]]]})
    lost = m.volume - one.volume
    # one vertical edge alone removes (4 - π)·10 ≈ 8.6 mm³; the corners at its ends blend too (documented), but
    # far less than rounding every edge would
    allv = m.volume - cadops.op_round_edges(m, {"radius": 2})[0].volume
    assert one.is_watertight and (4 - math.pi) * 10 * 0.9 < lost < allv / 3


def _new():
    r = c.post("/api/cad/new", json={"op": "sketch_extrude", "params": {"sketch": SQUARE, "distance": 10}, "title": "Bracket"})
    assert r.status_code == 200, r.text
    return r.json()


def test_api_history_replay_rename_appearance():
    p = _new()
    bid = p["id"]
    assert p["ops"][0]["op"] == "sketch_extrude" and len(p["bodies"]) == 1
    hole = {"sketch": {"entities": [{"id": "k", "type": "circle", "c": [10, 10], "r": 3}]}, "plane": {"origin": [0, 0, 10], "normal": [0, 0, 1]},
            "direction": "down", "distance": 10, "mode": "cut"}
    r = c.post(f"/api/edit/{bid}/op", json={"op": "sketch_extrude", "params": hole})
    assert r.status_code == 200, r.text
    v1 = r.json()["analysis"]["volume_mm3"]
    # edit step 1 (taller) -> step 2 (the hole) replays on top
    r = c.put(f"/api/edit/{bid}/step/1", json={"params": {**p["ops"][0]["params"], "distance": 20}})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["analysis"]["size_mm"][2] == pytest.approx(20, abs=1e-3) and j["analysis"]["volume_mm3"] > v1 and len(j["ops"]) == 2
    r = c.put(f"/api/cad/{bid}/step/2/name", json={"name": "Bolt hole"})
    assert r.status_code == 200 and r.json()["ops"][1]["name"] == "Bolt hole"
    r = c.put(f"/api/edit/{bid}/step/2", json={"params": {**hole, "distance": 5}})
    assert r.json()["ops"][1]["name"] == "Bolt hole"                 # name survives a re-edit
    assert c.put(f"/api/cad/{bid}/appearance", json={"bodies": {"0": {"color": "#ff8800", "finish": "gloss"}}}).status_code == 200
    assert c.put(f"/api/cad/{bid}/appearance", json={"bodies": {"0": {"color": "red"}}}).status_code == 400
    assert c.get(f"/api/cad/{bid}/bodies").json()["appearance"]["0"]["color"] == "#ff8800"
    r = c.post(f"/api/edit/{bid}/op", json={"op": "pattern", "params": {"kind": "linear", "count": 2, "step": [40, 0, 0]}})
    assert r.status_code == 200 and len(c.get(f"/api/cad/{bid}/bodies").json()["bodies"]) == 2
    assert c.post(f"/api/edit/{bid}/undo").status_code == 200
    assert len(c.get(f"/api/cad/{bid}/bodies").json()["bodies"]) == 1
    assert c.delete(f"/api/edit/{bid}/step/2").json()["ops"][0]["op"] == "sketch_extrude"


def test_api_sketch_helpers_and_errors():
    r = c.post("/api/cad/sketch/solve", json={"sketch": {**SQUARE, "constraints": [{"type": "length", "a": "a", "value": 30}]}})
    assert r.status_code == 200 and r.json()["ok"]
    r = c.post("/api/cad/sketch/regions", json={"sketch": SQUARE})
    assert r.json()["regions"][0]["area"] == pytest.approx(400)
    assert c.post("/api/cad/sketch/offset", json={"sketch": SQUARE, "id": "a", "distance": 2}).json()["entity"]["p0"] == pytest.approx([0, 2])
    assert c.post("/api/cad/sketch/solve", json={"sketch": {"entities": "x"}}).status_code == 400
    assert c.post("/api/cad/new", json={"op": "pattern", "params": {}}).status_code == 400
    open_line = {"entities": [{"id": "a", "type": "line", "p0": [0, 0], "p1": [5, 0]}]}
    assert c.post("/api/cad/new", json={"op": "sketch_extrude", "params": {"sketch": open_line}}).status_code == 422
