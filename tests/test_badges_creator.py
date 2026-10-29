"""Creator badge, public/private visibility, like milestones, and the win tally."""
from app.community import badges
from app.community.store import CHALLENGE_ENTRIES, CHALLENGES, ENGAGEMENT, LISTINGS, USERS
from tests.b1 import ADULT, client, photo_build


def _pub(c, title):
    r = c.post("/api/showcase", json={
        "build_id": photo_build(c), "title": title, "description": "d", "tags": ["lamp"],
        "accept_guidelines": True, "nsfw": False, "visibility": "public", "license_id": "cc-by-4.0",
    })
    assert r.status_code == 200, r.text
    return r.json()


def test_creator_badge_is_public_on_zeimapp_only():
    zach = client({**ADULT, "display_name": "Zach", "username": "ZeimApp"})
    badges.seed()
    me = zach.get("/api/me").json()
    mine = zach.get("/api/me/badges").json()
    row = next(b for b in mine["badges"] if b["id"] == "creator")
    assert row["earned"] is True and row["visibility"] == "public"
    profile = client().get(f"/api/users/{me['id']}")
    assert profile.status_code == 200
    assert any(b["id"] == "creator" and b["name"] == "Creator" for b in profile.json()["badges"])
    other = client({"display_name": "Not Zach", "dob": "1991-02-02", "username": "notzach"})
    assert all(b["id"] != "creator" or not b["earned"] for b in other.get("/api/me/badges").json()["badges"])
    badges.seed()
    assert sum(1 for u in USERS.read().values() if "creator" in (u.get("badges") or {})) == 1


def test_private_badges_stay_hidden_and_public_ones_show():
    assert badges._visibility(badges._BY_ID["tester"]) == "private"
    assert badges._visibility(badges._BY_ID["creator"]) == "public"
    assert badges._visibility(badges._BY_ID["first_slice"]) == "public"


def test_like_milestones_and_win_tally():
    saved = {s: s.read() for s in (LISTINGS, CHALLENGES, CHALLENGE_ENTRIES, ENGAGEMENT)}
    try:
        author = client({"display_name": "Liked", "dob": "1989-04-04"})
        item = _pub(author, "Liked lamp")
        fans = [client({"display_name": f"Fan{n}", "dob": "1992-05-05"}) for n in range(10)]
        for fan in fans:
            assert fan.post(f"/api/showcase/{item['id']}/like", json={"liked": True}).status_code == 200
        sid = next(s for s, u in USERS.read().items() if u.get("id") == author.get("/api/me").json()["id"])
        have = set((USERS.read()[sid].get("badges") or {}))
        assert "likes_10" in have
        assert "likes_50" not in have
        badges.award_winners([
            {"place": 1, "owner_sid": sid, "item_id": item["id"]},
            {"place": 1, "owner_sid": sid, "item_id": item["id"]},
        ], "ch_test")
        user = USERS.read()[sid]
        assert badges.win_tally(user) == 1
        assert "win_gold" in user["badges"]
        badges.award_winners([{"place": 2, "owner_sid": sid, "item_id": item["id"]}], "ch_test_2")
        user = USERS.read()[sid]
        assert badges.win_tally(user) == 2
        assert badges.win_label(2) == "Monthly winner ×2"
        body = author.get("/api/me/badges").json()
        assert body["win_tally"] == 2 and body["win_label"] == "Monthly winner ×2"
        pub = client().get(f"/api/users/{author.get('/api/me').json()['id']}").json()
        assert pub["win_label"] == "Monthly winner ×2"
        assert all(b["id"] != "tester" for b in pub["badges"])
    finally:
        for store, data in saved.items():
            store.write(data)
