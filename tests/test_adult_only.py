"""ZEIM is 18+ only (owner decision 2026-10-12): the sign-up gate, the soft network limit, 'Report underage user',
moderator suspension and the documented data-deletion step. No teen code paths remain."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from datetime import date
from app import config
from app.community import identity, privacy
from app.community.store import USERS, AGE_BLOCKS, LISTINGS
from tests.b1 import *


import pytest


@pytest.fixture(autouse=True)
def _close_my_reports():
    """Other tests take the OLDEST open report from the queue: leave none open behind."""
    yield
    from app.community import moderation
    for r in moderation.queue():
        moderation.resolve(r["id"], "dismiss")


def _dob(years_ago: int, days: int = 0) -> str:
    from datetime import datetime, timezone
    t = datetime.now(timezone.utc).date()                            # the server computes age on the UTC date
    try:
        d = t.replace(year=t.year - years_ago)
    except ValueError:                       # 29 Feb
        d = t.replace(year=t.year - years_ago, day=28)
    from datetime import timedelta
    return (d + timedelta(days=days)).isoformat()






def test_no_teen_code_paths_left():
    import app.community.privacy as p, app.community.identity as i, app.community.catalog as c
    for name in ("is_minor", "clamp_for_minor", "migrate_minors"):
        assert not hasattr(p, name)
    assert not hasattr(identity.Actor, "is_teen") and not hasattr(c, "viewer_sees_no_counts") and not hasattr(c, "audience_ok")
    for name in ("ADULT_AGE", "TEEN_PUBLIC_ENABLED", "TEEN_FOLLOWERS_ENABLED", "HIDE_COUNTS_FOR_MINORS"):
        assert not hasattr(config, name)
    me = client(ADULT).get("/api/me").json()
    assert "age_group" not in me and me["send"]["role"] == "adult"




def publish(c, bid, vis="public", title="Lamp"):
    return c.post("/api/showcase", json={"build_id": bid, "title": title, "accept_guidelines": True, "nsfw": False, "visibility": vis})


def test_report_underage_user_then_moderator_suspends_and_nothing_is_deleted():
    owner = client({"display_name": "Owner", "dob": "1999-09-09"}); uid = owner.get("/api/me").json()["id"]
    p = publish(owner, photo_build(owner)); assert p.status_code == 200, p.text
    pid = p.json()["id"]
    viewer = client()
    r = viewer.post(f"/api/showcase/{pid}/report", json={"reason": "underage_user", "details": "says they are 15"})
    assert r.status_code == 200 and r.json()["auto_hidden"] is False
    q = viewer.get("/api/moderation/queue", headers=ADMIN).json()["reports"]
    rep = next(x for x in q if x["id"] == r.json()["id"])
    assert rep["reason"] == "underage_user" and rep["account_id"] == uid and "reporter" not in rep
    assert viewer.post(f"/api/moderation/{rep['id']}/resolve", json={"action": "suspend"}).status_code == 403     # admin only
    assert viewer.post(f"/api/moderation/{rep['id']}/resolve", json={"action": "suspend"}, headers=ADMIN).status_code == 200
    me = owner.get("/api/me").json()
    assert me["suspended"] is True and me["send"]["role"] == "basic" and me["recovery"] is None
    assert viewer.get(f"/api/showcase/{pid}").status_code == 404                          # nobody else sees its content
    assert any(i["id"] == pid for i in LISTINGS.read()) and any(u["id"] == uid for u in USERS.read().values())
    assert owner.put(f"/api/showcase/{pid}/visibility", json={"visibility": "public"}).status_code == 403
    assert client(ADULT).post(f"/api/follow/{uid}").status_code in (403, 404)
    # undo
    assert viewer.post(f"/api/moderation/users/{uid}/unsuspend", headers=ADMIN).status_code == 200
    assert viewer.get(f"/api/showcase/{pid}").status_code == 404                          # the reported item stays hidden until restored
    assert viewer.post(f"/api/moderation/{rep['id']}/resolve", json={"action": "restore"}, headers=ADMIN).status_code == 200
    assert viewer.get(f"/api/showcase/{pid}").status_code == 200


def test_report_a_profile_directly_and_suspend_route():
    owner = client({"display_name": "Prof", "dob": "1995-01-01"}); uid = owner.get("/api/me").json()["id"]
    owner.put("/api/me/privacy", json={"profile": "public"})
    v = client()
    r = v.post(f"/api/users/{uid}/report", json={"reason": "underage_user"}); assert r.status_code == 200, r.text
    assert v.post("/api/users/nope/report", json={"reason": "underage_user"}).status_code == 404
    assert v.post(f"/api/moderation/users/{uid}/suspend", headers=ADMIN).status_code == 200
    assert v.get(f"/api/users/{uid}").status_code == 404
    assert v.post("/api/moderation/users/nope/suspend", headers=ADMIN).status_code == 404


def test_underage_reason_needs_an_account():
    from app.community import moderation
    import pytest
    with pytest.raises(ValueError):
        moderation.report("zo-gear-demo-x", "sid-x", "underage_user", "", None)


