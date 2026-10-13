"""People I follow (2026-10-13): signed-in makers can see and manage who they follow (Account > Privacy), by username only.
Before this you could follow from a project page and see a Following feed, but there was no list to unfollow from."""
import itertools
import os
from tests.b1 import client
from app.community import moderation

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_n = itertools.count()


def U(name="Maker"):
    c = client()
    me = c.post("/api/me/signup", json={"display_name": f"{name} Realname", "dob": "1984-04-04", "username": f"{name}{next(_n)}x"}).json()
    return c, me


def test_list_shows_usernames_never_display_names_and_unfollow_removes_them():
    fan, _ = U("Fan")
    a, am = U("Alpha"); b, bm = U("Bravo")
    for m in (am, bm):
        assert fan.post(f"/api/follow/{m['id']}").status_code == 200
    r = fan.get("/api/me/following")
    assert r.status_code == 200 and r.json()["enabled"] is True
    rows = r.json()["following"]
    assert [x["name"] for x in rows] == ["@" + am["username"], "@" + bm["username"]]
    assert all(x["available"] and x["profile_url"] == f"/u/{x['id']}" for x in rows)
    assert "Realname" not in r.text
    assert fan.delete(f"/api/follow/{am['id']}").status_code == 200
    assert [x["id"] for x in fan.get("/api/me/following").json()["following"]] == [bm["id"]]


def test_only_signed_in_makers_have_a_list_and_it_is_private_to_them():
    assert client().get("/api/me/following").status_code == 401
    fan, _ = U("Solo"); other, om = U("Other")
    fan.post(f"/api/follow/{om['id']}")
    assert other.get("/api/me/following").json()["following"] == []      # my list is not shown to the person I follow
    assert fan.get("/api/me/following").json()["following"][0]["id"] == om["id"]


def test_a_suspended_or_private_account_stays_listed_unnamed_so_it_can_still_be_unfollowed():
    fan, _ = U("Keep"); a, am = U("Gone"); b, bm = U("Quiet")
    fan.post(f"/api/follow/{am['id']}"); fan.post(f"/api/follow/{bm['id']}")
    assert moderation.suspend(am["id"], "test")
    assert b.put("/api/me/privacy", json={"profile": "private"}).status_code == 200
    rows = {x["id"]: x for x in fan.get("/api/me/following").json()["following"]}
    for uid, uname in ((am["id"], am["username"]), (bm["id"], bm["username"])):
        assert rows[uid]["available"] is False and rows[uid]["profile_url"] is None
        assert uname not in rows[uid]["name"] and rows[uid]["name"] == "an account that's no longer available"
    assert fan.delete(f"/api/follow/{am['id']}").status_code == 200
    assert am["id"] not in {x["id"] for x in fan.get("/api/me/following").json()["following"]}


def test_opting_out_of_following_still_clears_follows_both_ways():
    fan, _ = U("Opt"); c, cm = U("Out")
    fan.post(f"/api/follow/{cm['id']}")
    assert c.put("/api/me/privacy", json={"social": "off"}).status_code == 200      # existing rule: removes follows in both directions
    assert fan.get("/api/me/following").json()["following"] == []
    assert c.get("/api/me/following").json() == {"enabled": False, "following": []}


def test_account_panel_has_a_named_people_i_follow_list_with_unfollow_buttons():
    js = open(os.path.join(ROOT, "static", "community.js"), encoding="utf-8").read()
    assert 'id="pv_following" aria-expanded="false" aria-controls="pv_followingList">People I follow</button>' in js
    assert '"/api/me/following"' in js and 'data-unfollow=' in js and 'aria-label="Unfollow ${esc(x.name)}"' in js
    assert "esc(x.name)" in js and "display_name" not in js.split("const drawFollowing", 1)[1].split("$(\"#pv_followers\")", 1)[0]
