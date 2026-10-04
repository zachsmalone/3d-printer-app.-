"""Teens (13-17) are PRIVATE ONLY at launch: no Public, no Followers-only, no public profile, adults cannot follow them.
Safety S-03 / bugs B-03. Flags: TEEN_PUBLIC_ENABLED, TEEN_FOLLOWERS_ENABLED (both default off)."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from app import config
from app.community import privacy
from app.community.store import USERS, LISTINGS
from tests.b1 import *

TEEN2 = {"display_name": "Tom Teen", "dob": "2010-03-03"}


def publish(c, bid, vis=None, title="Lamp"):
    body = {"build_id": bid, "title": title, "accept_guidelines": True}
    if vis: body["visibility"] = vis
    return c.post("/api/showcase", json=body)


def test_teen_cannot_set_followers_or_public_anywhere():
    t = client(TEEN); bid = photo_build(t)
    for vis in ("public", "followers"):
        assert t.put(f"/api/builds/{bid}/visibility", json={"visibility": vis}).status_code == 403, vis
        assert publish(t, bid, vis).status_code == 403, vis
        assert t.put("/api/me/privacy", json={"profile": vis}).status_code == 403, vis
        assert t.put("/api/me/privacy", json={"default_visibility": vis}).status_code == 403, vis
    assert t.put(f"/api/builds/{bid}/visibility", json={"visibility": "private"}).status_code == 200
    p = publish(t, bid, "private"); assert p.status_code == 200 and p.json()["visibility"] == "private"
    assert t.put(f"/api/showcase/{p.json()['id']}/visibility", json={"visibility": "public"}).status_code == 403
    assert t.put(f"/api/showcase/{p.json()['id']}/visibility", json={"visibility": "followers"}).status_code == 403
    assert t.put("/api/me/privacy", json={"profile": "private", "default_visibility": "private"}).status_code == 200
    # edit projects too (same visibility route as builds)
    e = t.post("/api/edit/new", files={"file": ("b.stl", __import__("trimesh").creation.box([10, 10, 10]).export(file_type="stl"), "application/octet-stream")}).json()
    assert t.put(f"/api/builds/{e['id']}/visibility", json={"visibility": "public"}).status_code == 403
    me = t.get("/api/me").json()["privacy"]; assert me["profile"] == "private" and me["default_visibility"] == "private"


def test_adults_cannot_follow_teens_and_teens_are_not_listed():
    t = client(TEEN); a = client(ADULT); t2 = client(TEEN2)
    uid = t.get("/api/me").json()["id"]
    assert a.post(f"/api/follow/{uid}").status_code == 404           # no existence leak either
    assert t2.post(f"/api/follow/{uid}").status_code == 404           # teen-to-teen deferred
    assert client().get(f"/api/users/{uid}").status_code == 404 and client().get(f"/u/{uid}").status_code == 404
    assert a.get(f"/api/users/{uid}").status_code == 404
    # a teen may still follow an adult creator, but is never shown in the adult's follower list or count
    aid = a.get("/api/me").json()["id"]
    assert t.post(f"/api/follow/{aid}").status_code == 200
    assert a.get("/api/me/followers").json()["followers"] == []
    assert a.get(f"/api/users/{aid}").json()["followers"] == 0


def test_teen_flags_can_be_reopened_and_reclosed(monkeypatch):
    monkeypatch.setattr(config, "TEEN_FOLLOWERS_ENABLED", True)
    t = client(TEEN); bid = photo_build(t)
    assert t.put(f"/api/builds/{bid}/visibility", json={"visibility": "followers"}).status_code == 200
    assert t.put(f"/api/builds/{bid}/visibility", json={"visibility": "public"}).status_code == 403     # public flag still off
    monkeypatch.setattr(config, "TEEN_PUBLIC_ENABLED", True)
    assert t.put(f"/api/builds/{bid}/visibility", json={"visibility": "public"}).status_code == 200
    assert client().get(f"/api/builds/{bid}").status_code == 200
    # closing the flags again hides it at once (read-time clamp) ...
    monkeypatch.setattr(config, "TEEN_PUBLIC_ENABLED", False); monkeypatch.setattr(config, "TEEN_FOLLOWERS_ENABLED", False)
    assert client().get(f"/api/builds/{bid}").status_code == 404
    # ... and the startup migration rewrites the stored values
    stored = lambda: json.loads((config.OUT / bid / "meta.json").read_text())["visibility"]
    assert stored() == "public"
    privacy.migrate_minors(); assert stored() == "private"


def test_existing_teen_data_migrated_to_private(monkeypatch):
    monkeypatch.setattr(config, "TEEN_PUBLIC_ENABLED", True); monkeypatch.setattr(config, "TEEN_FOLLOWERS_ENABLED", True)
    t = client(TEEN); a = client(ADULT)
    assert t.put("/api/me/privacy", json={"profile": "public", "default_visibility": "followers"}).status_code == 200
    pid = publish(t, photo_build(t), "public", "Old teen lamp").json()["id"]
    uid = t.get("/api/me").json()["id"]; assert a.post(f"/api/follow/{uid}").status_code == 200
    assert client().get(f"/api/showcase/{pid}").status_code == 200
    monkeypatch.setattr(config, "TEEN_PUBLIC_ENABLED", False); monkeypatch.setattr(config, "TEEN_FOLLOWERS_ENABLED", False)
    r = privacy.migrate_minors(); assert r["users"] >= 2 and r["projects"] >= 1 and r["follows"] >= 1
    assert client().get(f"/api/showcase/{pid}").status_code == 404 and a.get(f"/api/showcase/{pid}").status_code == 404
    assert t.get(f"/api/showcase/{pid}").status_code == 200             # owner still has it
    pv = t.get("/api/me").json()["privacy"]; assert pv["profile"] == "private" and pv["default_visibility"] == "private"
    assert [l["visibility"] for l in LISTINGS.read() if l["id"] == pid] == ["private"]
    assert uid not in a.get("/api/me").json()["following"]
    assert client().get(f"/api/users/{uid}").status_code == 404
    for tab in ("trending", "free"):
        assert pid not in [i["id"] for i in client().get(f"/api/showcase?tab={tab}").json()["items"]]


def test_adults_unaffected():
    a = client(ADULT); bid = photo_build(a)
    assert a.put(f"/api/builds/{bid}/visibility", json={"visibility": "public"}).status_code == 200
    assert a.put("/api/me/privacy", json={"profile": "followers"}).status_code == 200
    assert publish(a, bid, "public").status_code == 200
