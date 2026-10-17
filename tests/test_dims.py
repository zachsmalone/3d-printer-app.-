import io

import pytest
import trimesh
from fastapi.testclient import TestClient

from app.core import dims
from app.main import app


def test_check_dims_rules():
    assert dims.check_dims({"wall": 2, "a_1": 3.5}) == {"wall": 2.0, "a_1": 3.5}
    for bad in ({"1x": 1}, {"a b": 1}, {"x": "3"}, {"x": True}, {"x": float("nan")}, {"x": 1e9}, [1], {f"d{i}": 1 for i in range(51)}):
        with pytest.raises(dims.DimError):
            dims.check_dims(bad)


def test_resolve_substitutes_nested_and_skips_text():
    p = {"width": "$w", "plane": {"point": [0, 0, "$z"]}, "mode": "add"}
    assert dims.resolve("on_face", p, {"w": 4, "z": 2}) == {"width": 4, "plane": {"point": [0, 0, 2]}, "mode": "add"}
    assert dims.resolve("text", {"text": "$w"}, {"w": 4}) == {"text": "$w"}
    with pytest.raises(dims.DimError):
        dims.resolve("on_face", {"width": "$nope"}, {})


def _project(c):
    box = trimesh.creation.box((40, 40, 10)).export(file_type="stl")
    j = c.post("/api/edit/new", files={"file": ("p.stl", io.BytesIO(box), "model/stl")}).json()
    return j["id"] if "id" in j else j["project"]["id"]


def test_changing_a_dimension_replays_the_steps():
    c = TestClient(app)
    bid = _project(c)
    assert c.put(f"/api/edit/{bid}/dims", json={"dims": {"boss": 6.0}}).status_code == 200
    f = c.get(f"/api/edit/{bid}/features").json()
    top = max((p for p in f["planes"] if p["normal"][2] > 0.9), key=lambda p: p["origin"][2])
    op = {"op": "on_face", "params": {"shape": "cylinder", "mode": "add", "plane": {"normal": top["normal"], "point": top["origin"]},
                                      "diameter": "$boss", "height": 5}}
    r = c.post(f"/api/edit/{bid}/op", json=op)
    assert r.status_code == 200, r.text
    vol1 = r.json()["analysis"]["volume_mm3"]
    assert r.json()["dims"] == {"boss": 6.0}
    r2 = c.put(f"/api/edit/{bid}/dims", json={"dims": {"boss": 10.0}})
    assert r2.status_code == 200
    assert r2.json()["analysis"]["volume_mm3"] > vol1 + 100                 # a wider boss: more volume
    assert r2.json()["ops"][-1]["params"]["diameter"] == "$boss"            # the step still stores the name


def test_cannot_drop_a_used_name_or_use_an_unknown_one_or_break_the_model():
    c = TestClient(app)
    bid = _project(c)
    c.put(f"/api/edit/{bid}/dims", json={"dims": {"d": 6}})
    f = c.get(f"/api/edit/{bid}/features").json()
    top = max((p for p in f["planes"] if p["normal"][2] > 0.9), key=lambda p: p["origin"][2])
    plane = {"normal": top["normal"], "point": top["origin"]}
    bad = c.post(f"/api/edit/{bid}/op", json={"op": "on_face", "params": {"shape": "cylinder", "mode": "add", "plane": plane, "diameter": "$ghost", "height": 5}})
    assert bad.status_code == 422 and "ghost" in bad.text
    assert c.post(f"/api/edit/{bid}/op", json={"op": "on_face", "params": {"shape": "cylinder", "mode": "add", "plane": plane, "diameter": "$d", "height": 5}}).status_code == 200
    assert c.put(f"/api/edit/{bid}/dims", json={"dims": {}}).status_code == 422            # still used
    r = c.put(f"/api/edit/{bid}/dims", json={"dims": {"d": 500}})                        # boss wider than the plate: detached/invalid or fine, but never half-applied
    after = c.get(f"/api/edit/{bid}").json()
    assert after["dims"] == ({"d": 500.0} if r.status_code == 200 else {"d": 6.0})
    assert c.put(f"/api/edit/{bid}/dims", json={"dims": {"1bad": 1}}).status_code == 400
