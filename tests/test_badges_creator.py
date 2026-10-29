"""Creator badge, public/private visibility, like milestones, and the win tally."""
from pathlib import Path

from app.community import badges
from app.community.store import CHALLENGE_ENTRIES, CHALLENGES, ENGAGEMENT, LISTINGS, USERS
from tests.b1 import ADULT, client, photo_build

ROOT = Path(__file__).resolve().parents[1]


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
    assert row["earned"] is True and row["name"] == "Creator" and row["visibility"] == "public"
    profile = client().get(f"/api/users/{me['id']}")
    assert profile.status_code == 200
    assert any(b["id"] == "creator" and b["name"] == "Creator" for b in profile.json()["badges"])
    item = _pub(zach, "Founder lamp")
    post = client().get(f"/api/showcase/{item['id']}")
    assert post.status_code == 200, post.text
    on_post = post.json()["creator_badges"]
    assert any(b["id"] == "creator" and b["name"] == "Creator" for b in on_post)
    assert all(b["id"] != "tester" for b in on_post)
    other = client({"display_name": "Not Zach", "dob": "1991-02-02", "username": "notzach"})
    assert all(b["id"] != "creator" or not b["earned"] for b in other.get("/api/me/badges").json()["badges"])
    badges.seed()
    assert sum(1 for u in USERS.read().values() if "creator" in (u.get("badges") or {})) == 1
    box = (ROOT / "static/badges.js").read_text(encoding="utf-8")
    assert "creator:" in box and "M4 16h16l-1.4-7" in box
    ui = (ROOT / "static/community.js").read_text(encoding="utf-8")
    assert ui.count('b.id === "creator"') >= 2
    assert 'class="pill">Creator</span>' in ui


def test_badges_are_public_unless_marked_private(monkeypatch):
    """Public is the default. A private badge stays on the owner's box only."""
    for spec in badges.CATALOG:
        if spec["id"] == "tester":
            assert badges._visibility(spec) == "private"
        else:
            assert badges._visibility(spec) == "public"
    omitted = {"id": "plain_mark", "name": "Plain"}
    assert badges._visibility(omitted) == "public"
    secret = {"id": "quiet_mark", "name": "Quiet", "visibility": "private", "auto": True, "how": ""}
    monkeypatch.setattr(badges, "CATALOG", (*badges.CATALOG, secret))

    owner = client({"display_name": "Quiet Owner", "dob": "1990-03-03", "username": "quietowner"})
    me = owner.get("/api/me").json()
    sid = next(s for s, u in USERS.read().items() if u.get("id") == me["id"])
    USERS.update(lambda d: d[sid].setdefault("badges", {}).__setitem__(
        "quiet_mark", {"earned_at": "2026-10-01T00:00:00+00:00"}))
    assert badges.record(sid, "fdm_slice")[0]["id"] == "first_slice"
    mine = owner.get("/api/me/badges").json()
    quiet = next(b for b in mine["badges"] if b["id"] == "quiet_mark")
    assert quiet["earned"] is True and quiet["visibility"] == "private"
    assert next(b for b in mine["badges"] if b["id"] == "first_slice")["visibility"] == "public"

    stranger = client()
    profile = stranger.get(f"/api/users/{me['id']}")
    assert profile.status_code == 200
    shown = {b["id"] for b in profile.json()["badges"]}
    assert "quiet_mark" not in shown and "first_slice" in shown
    item = _pub(owner, "Quiet lamp")
    on_post = {b["id"] for b in stranger.get(f"/api/showcase/{item['id']}").json()["creator_badges"]}
    assert "quiet_mark" not in on_post and "first_slice" in on_post

    hort = {
        "id": "hort-vis",
        "username": "cc0hort",
        "badges": {
            "tester": {"earned_at": "2020-01-01T00:00:00+00:00"},
            "official_og": {"earned_at": "2020-01-01T00:00:00+00:00"},
        },
    }
    box = badges._rows(hort, owner=True)
    tester = next(b for b in box if b["id"] == "tester")
    assert tester["earned"] is True and tester["visibility"] == "private" and tester["name"] == "Tester"
    public_ids = {b["id"] for b in badges.public_earned(hort)}
    assert "tester" not in public_ids and "official_og" in public_ids
    copied = {**hort, "username": "notcc0hort"}
    assert all(b["id"] != "tester" for b in badges._rows(copied, owner=True))


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
