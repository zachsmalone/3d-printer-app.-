"""SEND-1: who may get a build OUT of ZEIM (design-ios-send.md 2.2), enforced on the server.
Download always; share/printer/slicer links only for adults; suspended / signed-out never. (Class/teacher paths removed 2026-10-12.)"""
import logging
import pytest
from app import config
from tests import b1
from tests.b1 import client, photo_build, ADULT, SUSPENDED, UNDER18


@pytest.fixture
def shared(monkeypatch):
    monkeypatch.setattr(config, "MODE", "shared")
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "https://zeim.example.org")


def caps(c):
    return c.get("/api/me").json()["send"]


def test_adult_gets_everything_suspended_and_unknown_get_download_only(shared):
    a, t, anon = client(ADULT), client(SUSPENDED), client()
    k = caps(a); assert {x: k[x] for x in ("download", "share", "printer", "links", "role")} == {"download": True, "share": True, "printer": True, "links": True, "role": "adult"}
    for c, role in ((t, "basic"), (anon, "basic")):          # signed-out visitors and suspended accounts: Download only
        k = caps(c)
        assert k["role"] == role and k["download"] and not (k["share"] or k["printer"] or k["links"]) and "teacher" not in k



def test_local_mode_owner_keeps_working_but_suspended_accounts_still_blocked(monkeypatch):
    monkeypatch.setattr(config, "MODE", "local")
    anon = client(); bid = photo_build(anon)
    assert caps(anon)["role"] == "adult" and anon.get("/api/print/" + bid + "/links").status_code == 200
    sus = client(SUSPENDED); tb = photo_build(sus)
    assert sus.get(f"/api/print/{tb}/links").status_code == 403


def test_sharetest_page_is_hidden_adult_only_and_labelled_untested(shared):
    c = client()
    r = c.get("/sharetest")
    assert r.status_code == 200 and "UNTESTED" in r.text and "noindex" in r.headers["x-robots-tag"]
    assert "sharetest" not in open("static/index.html").read()                    # not linked from the app
    assert c.get("/api/sharetest/file.stl").status_code == 403                      # visitors/suspended: no
    assert client(SUSPENDED).get("/api/sharetest/file.3mf").status_code == 403
    a = client(ADULT)
    for fmt in ("stl", "obj", "3mf"):
        f = a.get(f"/api/sharetest/file.{fmt}"); assert f.status_code == 200 and len(f.content) > 100
    assert a.get("/api/sharetest/file.exe").status_code == 404
