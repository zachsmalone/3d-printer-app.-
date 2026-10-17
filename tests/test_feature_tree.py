import io

import trimesh
from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)


def _project():
    stl = trimesh.creation.box((20, 20, 20)).export(file_type="stl")
    j = c.post("/api/edit/new", files={"file": ("b.stl", io.BytesIO(stl), "model/stl")}).json()
    return j["id"] if "id" in j else j["project"]["id"]


def _op(bid, op, params):
    r = c.post(f"/api/edit/{bid}/op", json={"op": op, "params": params})
    assert r.status_code == 200, r.text
    return r.json()


def test_edit_a_step_replays_later_steps():
    bid = _project()
    _op(bid, "translate", {"dx": 10})
    p = _op(bid, "scale", {"factor": 2})
    assert p["ops"][0]["params"]["dx"] == 10 and p["ops"][0]["editable"]
    r = c.put(f"/api/edit/{bid}/step/1", json={"params": {"dx": 50}})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["ops"][0]["params"]["dx"] == 50 and "50" in p["ops"][0]["label"] and len(p["ops"]) == 2
    assert c.get(f"/api/edit/{bid}").json()["head"] == 2


def test_delete_a_step_and_bad_edits_change_nothing():
    bid = _project()
    _op(bid, "translate", {"dx": 10})
    _op(bid, "rotate", {"rz": 45})
    before = c.get(f"/api/edit/{bid}").json()
    assert c.put(f"/api/edit/{bid}/step/9", json={"params": {}}).status_code == 422
    assert c.put(f"/api/edit/{bid}/step/1", json={"params": "x"}).status_code == 400
    assert c.get(f"/api/edit/{bid}").json()["ops"] == before["ops"]
    r = c.delete(f"/api/edit/{bid}/step/1")
    assert r.status_code == 200 and [o["op"] for o in r.json()["ops"]] == ["rotate"]
    c.post(f"/api/edit/{bid}/undo")
    assert c.get(f"/api/edit/{bid}").json()["head"] == 0
