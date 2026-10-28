"""The repaired file opens in the FDM Slicer on the server. The browser does not upload it again."""
import io

import numpy as np
import pytest
import trimesh

from tests import b1  # noqa: F401  (isolated PHOTO3D_OUT / DATA before the app is imported)
from tests.b1 import ADULT, client

from app.community.identity import COOKIE
from app.services.history import store


def _stl(m):
    return trimesh.exchange.stl.export_stl(m)


def _cube(side=20):
    b = trimesh.creation.box((side,) * 3)
    b.apply_translation((side / 2, side / 2, side / 2))
    return trimesh.Trimesh(b.vertices, b.faces, process=False)


def _holey():
    m = _cube()
    f = np.delete(m.faces, [0, 1], axis=0)
    return _stl(trimesh.Trimesh(m.vertices, f, process=False))


def _repair(c, name="broken.stl", data=None):
    r = c.post("/api/repair", files={"file": (name, io.BytesIO(data if data is not None else _holey()), "application/octet-stream")})
    assert r.status_code == 200, r.text
    return r.json()


def _open(c, rid, **data):
    return c.post(f"/api/repair/{rid}/slicer", data=data)


@pytest.fixture
def c():
    return client(ADULT)


def test_open_uses_the_repaired_bytes_once_and_then_the_same_project(c):
    j = _repair(c)
    sid = c.cookies.get(COOKIE)
    before = len(store.list(sid))
    first = _open(c, j["id"])
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["created"] is True and body["reused"] is False and body["same"] is False
    hid = body["id"]
    assert len(hid) == 12 and body["url"] == f"/?edit={hid}#slicer"
    assert len(store.list(sid)) == before + 1
    repaired = c.get(j["download_url"]).content
    original = c.get(f"/api/edit/{hid}/original").content
    assert original == repaired
    proj = c.get(f"/api/edit/{hid}").json()
    assert proj["title"] == "Repaired model"
    assert proj["beginner"] is True
    assert proj["base"]["type"] == "repair" and proj["base"]["from_repair"] == j["id"]
    assert proj["analysis"]["watertight"] is True
    assert proj["analysis"]["volume_mm3"] == pytest.approx(8000, rel=0.01)
    again = _open(c, j["id"], edit=hid, beginner="false")
    assert again.status_code == 200, again.text
    assert again.json() == {**body, "created": False, "reused": True, "same": True}
    assert c.get(f"/api/edit/{hid}").json()["beginner"] is True
    assert len(store.list(sid)) == before + 1
    other_file = _repair(c)
    crossed = _open(c, other_file["id"], edit=hid)
    assert crossed.status_code == 200, crossed.text
    assert crossed.json()["id"] != hid and crossed.json()["same"] is False and crossed.json()["created"] is True
    assert c.get(f"/api/edit/{hid}").json()["base"]["from_repair"] == j["id"]
    assert c.get(f"/api/edit/{crossed.json()['id']}").json()["base"]["from_repair"] == other_file["id"]
    anon = client()
    lone = _repair(anon, data=_holey())
    opened = _open(anon, lone["id"])
    assert opened.status_code == 200, opened.text
    assert opened.json()["created"] is True
    assert client().get(f"/api/edit/{opened.json()['id']}").status_code == 404


def test_a_different_project_is_not_replaced_and_the_file_name_is_not_the_title(c):
    kept = c.post(
        "/api/edit/new",
        files={"file": ("kept.stl", io.BytesIO(_stl(_cube(10))), "application/octet-stream")},
        data={"title": "Desk clip"},
    )
    assert kept.status_code == 200, kept.text
    kid = kept.json()["id"]
    j = _repair(c, "MiaJohnson_clip.stl")
    opened = _open(c, j["id"], edit=kid)
    assert opened.status_code == 200, opened.text
    body = opened.json()
    assert body["id"] != kid and body["same"] is False and body["created"] is True
    assert "MiaJohnson" not in opened.text
    still = c.get(f"/api/edit/{kid}").json()
    assert still["title"] == "Desk clip"
    assert still["base"]["type"] == "upload"
    proj = c.get(f"/api/edit/{body['id']}").json()
    assert proj["title"] == "Repaired model" and "MiaJohnson" not in proj["title"]
    other = client(ADULT)
    assert other.post(f"/api/repair/{j['id']}/slicer").status_code == 404
    assert other.get(f"/api/edit/{body['id']}").status_code == 404
    assert c.get(j["download_url"]).status_code == 200


def test_missing_repair_does_not_invent_a_project(c):
    assert c.post("/api/repair/zzzz/slicer").status_code == 404
    missing = "ab" * 8
    lost = _open(c, missing)
    assert lost.status_code == 404
    assert isinstance(lost.json()["detail"], str)
    sid = c.cookies.get(COOKIE)
    assert store.list(sid) == []
