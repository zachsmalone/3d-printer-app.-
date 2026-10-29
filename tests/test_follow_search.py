"""User search, follow notices, and the post bell."""
from app.community.store import LISTINGS
from tests.b1 import client, photo_build


def _pub(c, title, **extra):
    body = {"build_id": photo_build(c), "title": title, "description": "d", "tags": ["lamp"],
            "accept_guidelines": True, "nsfw": False, "visibility": "public", "license_id": "cc-by-4.0"}
    body.update(extra)
    r = c.post("/api/showcase", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_search_finds_a_username_and_never_an_email():
    maker = client({"display_name": "Search Maker", "dob": "1990-01-01", "username": "searchlamp"})
    me = maker.get("/api/me").json()
    found = client().get("/api/users/search", params={"q": "@search"}).json()["users"]
    assert any(u["id"] == me["id"] and u["username"] == "searchlamp" for u in found)
    assert all("email" not in u and "@" not in u["username"] for u in found)
    assert client().get("/api/users/search", params={"q": "s"}).json()["users"] == []


def test_follow_and_a_new_post_notify_without_email():
    author = client({"display_name": "Author", "dob": "1988-03-03", "username": "postauthor"})
    fan = client({"display_name": "Fan", "dob": "1987-04-04", "username": "postfan"})
    aid = author.get("/api/me").json()["id"]
    fid = fan.get("/api/me").json()["id"]
    assert fan.post(f"/api/follow/{aid}").status_code == 200
    notes = author.get("/api/me/notifications").json()
    assert notes["unread"] == 1
    assert notes["notifications"][0]["text"] == "@postfan followed you"
    assert "email" not in notes["notifications"][0]["text"]
    assert notes["notifications"][0]["user_id"] == fid
    item = _pub(author, "Followed lamp")
    bell = fan.get("/api/me/notifications").json()
    assert bell["unread"] >= 1
    hit = next(n for n in bell["notifications"] if n["kind"] == "post")
    assert hit["item_id"] == item["id"]
    assert hit["text"].startswith("@postauthor")
    assert "email" not in hit["text"]
    assert fan.post("/api/me/notifications/read", json={"id": hit["id"]}).json()["unread"] == 0
    assert LISTINGS.read()
