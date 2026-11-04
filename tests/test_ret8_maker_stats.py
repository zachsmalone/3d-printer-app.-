from fastapi.testclient import TestClient


def _client(sid_cookie=None):
    from app.main import app
    return TestClient(app)


def test_tip_clicks_counted_once_and_private(tmp_path):
    from app.community import catalog, makerstats
    from types import SimpleNamespace
    owner = SimpleNamespace(sid="owner-sid", user=None)
    item = {"id": "it_r8", "title": "Lamp", "owner_sid": "owner-sid", "tip_url": "https://ko-fi.com/x", "hidden": False, "_dlers": ["a", "b"], "_likers": ["a"]}
    orig_all, orig_mine = catalog._all, catalog.mine
    catalog._all = lambda: [item]; catalog.mine = lambda a: [item] if a.sid == "owner-sid" else []
    try:
        makerstats.TIPCLICKS.write({})
        assert makerstats.record_tip_click("it_r8", "v1") is True
        assert makerstats.record_tip_click("it_r8", "v1") is False
        assert makerstats.record_tip_click("it_r8", "owner-sid") is False
        assert "v1" not in str(makerstats.TIPCLICKS.read())
        row = makerstats.for_owner(owner)[0]
        assert row["tip_clicks"] == 1 and row["downloads"] == 2 and row["likes"] == 1
        assert makerstats.for_owner(SimpleNamespace(sid="someone", user=None)) == []
    finally:
        catalog._all, catalog.mine = orig_all, orig_mine


def test_routes_exist():
    c = _client()
    assert c.get("/api/me/maker-stats").json()["items"] == []
    r = c.post("/api/showcase/nope/tipclick", headers={"X-Requested-With": "zeim"})
    assert r.status_code == 200 and r.json()["counted"] is False
