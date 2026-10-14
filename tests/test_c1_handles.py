"""Public profile, its page, follower lists and the moderator queue show @username, never the display name (which may be a real name)."""
from tests.b1 import client, photo_build, ADMIN

import itertools
_n = itertools.count(1)


def _adult_with_item():
    a = client(); me = a.post("/api/me/signup", json={"display_name": "Margaret Realname", "dob": "1982-03-04", "username": f"MossMaker{next(_n)}"}).json()
    it = a.post("/api/showcase", json={"build_id": photo_build(a), "title": "Lamp", "description": "d", "tags": [], "accept_guidelines": True, "nsfw": False, "visibility": "public"}).json()
    return a, me, it


def test_public_profile_and_page_show_the_username_not_the_real_name():
    a, me, it = _adult_with_item()
    v = client()
    prof = v.get(f"/api/users/{me['id']}")
    assert prof.status_code == 200 and prof.json()["display_name"] == "@" + me["username"]
    page = v.get(f"/u/{me['id']}").text
    for r in (prof.text, page):
        assert "Margaret" not in r and "Realname" not in r
    assert "@" + me["username"] in page


def test_moderator_queue_names_the_creator_by_username():
    a, me, it = _adult_with_item()
    client().post(f"/api/showcase/{it['id']}/report", json={"reason": "other"})
    q = client().get("/api/moderation/queue", headers=ADMIN)
    row = next(r for r in q.json()["reports"] if r["item_id"] == it["id"])
    assert row["preview"]["creator"] == "@" + me["username"]
    assert "Margaret" not in q.text and "Realname" not in q.text


def test_follower_list_uses_usernames():
    a, me, it = _adult_with_item()
    f = client(); fm = f.post("/api/me/signup", json={"display_name": "Bob Secretname", "dob": "1980-01-01", "username": f"BobPrints{next(_n)}"}).json()
    assert f.post(f"/api/follow/{me['id']}").status_code == 200
    r = a.get("/api/me/followers")
    assert "Secretname" not in r.text and "@" + fm["username"] in r.text
