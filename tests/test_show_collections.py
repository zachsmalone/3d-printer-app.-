"""Showcase collections: creators group their own models; public adults browse them."""
import pathlib

import pytest

from app.community import collections as cols
from app.community.store import COLLECTIONS, ENGAGEMENT, LISTINGS, MODERATION, PREFS, PRINTS
from tests.b1 import client, photo_build


@pytest.fixture(autouse=True)
def _fresh():
    snap = {s: s.read() for s in (LISTINGS, ENGAGEMENT, PREFS, PRINTS, MODERATION, COLLECTIONS)}
    yield
    for s, was in snap.items():
        s.write(was)


def U(n="Maker"):
    return client({"display_name": n, "dob": "1990-01-01"})


def publish(c, title="Pub", visibility="public"):
    r = c.post("/api/showcase", json={"build_id": photo_build(c), "title": title, "description": "d",
                                      "tags": ["lamp"], "accept_guidelines": True, "nsfw": False,
                                      "visibility": visibility})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_lifecycle_own_models_public_by_default():
    a, b = U("Cola"), U("Colb")
    mine = publish(a, "My lamp")
    theirs = publish(b, "Their lamp")
    r = a.post("/api/me/collections", json={"name": "Desk stuff"})
    assert r.status_code == 200, r.text
    col = r.json()
    assert col["public"] is True and col["count"] == 0 and col["mine"]
    # only own models
    assert a.post(f"/api/me/collections/{col['id']}/items", json={"item_id": theirs, "on": True}).status_code == 403
    r = a.post(f"/api/me/collections/{col['id']}/items", json={"item_id": mine, "on": True})
    assert r.status_code == 200 and r.json()["count"] == 1 and r.json()["on"] is True
    assert a.get(f"/api/me/collections?item={mine}").json()["holding"] == [col["id"]]
    # public: others see it on the profile and can open it
    uid = a.get("/api/me").json()["id"]
    listed = b.get(f"/api/users/{uid}/collections").json()["collections"]
    assert [c["id"] for c in listed] == [col["id"]]
    j = b.get(f"/api/collections/{col['id']}").json()
    assert [x["id"] for x in j["items"]] == [mine]
    # rename + remove item + delete
    assert a.put(f"/api/me/collections/{col['id']}", json={"name": "Shelf"}).json()["name"] == "Shelf"
    assert a.post(f"/api/me/collections/{col['id']}/items", json={"item_id": mine, "on": False}).json()["count"] == 0
    assert a.delete(f"/api/me/collections/{col['id']}").status_code == 200
    assert a.get("/api/me/collections").json()["collections"] == []


def test_private_collection_hidden_from_others():
    a, b = U("Priva"), U("Privb")
    iid = publish(a)
    cid = a.post("/api/me/collections", json={"name": "Draft", "public": False}).json()["id"]
    a.post(f"/api/me/collections/{cid}/items", json={"item_id": iid, "on": True})
    assert b.get(f"/api/collections/{cid}").status_code == 404
    uid = a.get("/api/me").json()["id"]
    assert b.get(f"/api/users/{uid}/collections").json()["collections"] == []
    assert a.get(f"/api/collections/{cid}").status_code == 200
    assert a.put(f"/api/me/collections/{cid}", json={"public": True}).json()["public"] is True
    assert b.get(f"/api/collections/{cid}").status_code == 200


def test_private_project_drops_out_for_viewers():
    a, b = U("Dropa"), U("Dropb")
    iid = publish(a)
    cid = a.post("/api/me/collections", json={"name": "Shown"}).json()["id"]
    a.post(f"/api/me/collections/{cid}/items", json={"item_id": iid, "on": True})
    a.put(f"/api/showcase/{iid}/visibility", json={"visibility": "private"})
    assert b.get(f"/api/collections/{cid}").json()["items"] == []
    # owner still sees their own private project in the collection
    assert [x["id"] for x in a.get(f"/api/collections/{cid}").json()["items"]] == [iid]


def test_rules_and_limits():
    c = U("Rules")
    anon = client()
    assert anon.post("/api/me/collections", json={"name": "a"}).status_code == 401
    assert c.post("/api/me/collections", json={"name": ""}).status_code == 400
    assert c.post("/api/me/collections", json={"name": "x" * 61}).status_code == 400
    assert c.post("/api/me/collections", json={"name": "Dup"}).status_code == 200
    assert c.post("/api/me/collections", json={"name": "dup"}).status_code == 400
    cid = c.get("/api/me/collections").json()["collections"][0]["id"]
    assert c.post(f"/api/me/collections/{cid}/items", json={"item_id": "nope"}).status_code == 404
    # others cannot rename or delete
    o = U("Other")
    assert o.put(f"/api/me/collections/{cid}", json={"name": "x"}).status_code == 404
    assert o.delete(f"/api/me/collections/{cid}").status_code == 404


def test_name_is_filtered():
    c = U("Filt")
    r = c.post("/api/me/collections", json={"name": "send nudes"})
    assert r.status_code >= 400


def test_unit_helpers():
    rec = cols.create("s1", "u1", "Lamps")
    assert cols.of_owner("s1")[0]["id"] == rec["id"]
    cols.set_item("s1", rec["id"], "p1", True)
    assert cols.holding("s1", "p1") == [rec["id"]]
    cols.rename("s1", rec["id"], "Shelves")
    assert cols.get(rec["id"])["name"] == "Shelves"
    assert cols.delete("s1", rec["id"])
    assert cols.of_owner("s1") == []


def test_static_ui_wired():
    root = pathlib.Path(__file__).resolve().parents[1] / "static"
    js = (root / "community.js").read_text()
    html = (root / "index.html").read_text()
    assert "/api/me/collections" in js and "/api/users/" in js and "Collections" in js
    assert "colHost" in html and "i-folder" in html
    assert "collections.js" not in html   # wired in community.js, not a separate GPL-ish blob
