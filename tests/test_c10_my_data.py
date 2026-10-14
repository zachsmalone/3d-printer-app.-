"""What ZEIM knows about you: live summary, JSON export, Delete everything I made (UI-backed API)."""
import json
from tests.b1 import client, photo_build, ADULT


def test_me_data_lists_builds_and_shared_and_says_what_is_not_collected():
    c = client(ADULT)
    b = photo_build(c)
    c.post("/api/showcase", json={"build_id": b, "title": "My lamp", "accept_guidelines": True, "nsfw": False, "visibility": "private"})
    d = c.get("/api/me/data").json()
    assert d["signed_up"] is True
    assert d["builds_count"] >= 1 and any(x["id"] == b for x in d["builds"])
    assert d["shared_count"] >= 1 and any(x["title"] == "My lamp" for x in d["shared"])
    assert d["account"]["username"]
    assert "phone number" in " ".join(d["not_collected"]).lower()
    assert d["enabled"] in (True, False)          # legacy personalization keys still present
    assert "interests" in d and "searches" in d


def test_me_export_is_a_json_download_with_no_store_cache():
    c = client(ADULT)
    photo_build(c)
    r = c.get("/api/me/export")
    assert r.status_code == 200
    assert "attachment" in r.headers.get("content-disposition", "").lower()
    assert "zeim-my-data.json" in r.headers.get("content-disposition", "")
    assert r.headers.get("cache-control") == "no-store"
    body = r.json()
    assert body["builds_count"] >= 1
    assert body["exported_at"].endswith("Z")
    assert "Metadata only" in body["export_note"]
    # round-trip through dumps so we know it is plain JSON (no bytes)
    json.dumps(body)


def test_guest_me_data_has_no_account_but_still_lists_session_builds():
    c = client()          # anonymous browser session
    b = photo_build(c)
    d = c.get("/api/me/data").json()
    assert d["signed_up"] is False and d["account"] is None
    assert any(x["id"] == b for x in d["builds"])
