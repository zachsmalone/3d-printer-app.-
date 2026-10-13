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


def test_18_today_is_allowed_one_day_short_is_refused_with_a_friendly_message_and_nothing_stored():
    assert config.MIN_SIGNUP_AGE == 18
    young = _dob(18, days=1)                                         # turns 18 tomorrow
    r = TestClient(app).post("/api/me/signup", json={"display_name": "Almost", "dob": young})
    assert r.status_code == 403
    msg = r.json()["detail"]
    assert "18" in msg and "without an account" in msg and "adult account holder" in msg
    for w in ("kid", "teen", "grown-up"):
        assert w not in msg.lower()
    blob = "".join(p.read_text() for p in config.DATA.glob("*.json"))
    assert young not in blob and "Almost" not in blob                # the date (and name) of a refused attempt are not stored
    ok = TestClient(app).post("/api/me/signup", json={"display_name": "Just18", "dob": _dob(18)})
    assert ok.status_code == 200 and ok.json()["signed_up"] and "recovery_code" in ok.json()


def test_under_18_refusal_locks_that_browser_only_and_a_soft_ip_limit_never_locks_a_network_after_a_few(monkeypatch):
    from app.api import community as _c
    from app.core import ratelimit; ratelimit.reset()
    monkeypatch.setattr(config, "AGE_IP_LOCK_MINUTES", 15)
    monkeypatch.setattr(_c, "_ip", lambda r: "198.51.100.40")
    for _ in range(3):                                               # three different under-18 browsers on one home/office address
        k = TestClient(app)
        assert k.post("/api/me/signup", json={"display_name": "Y", "dob": "2012-01-01"}).status_code == 403
        assert k.post("/api/me/signup", json={"display_name": "Y", "dob": "1980-01-01"}).status_code == 403    # that browser stays locked
    assert TestClient(app).post("/api/me/signup", json={"display_name": "Parent", "dob": "1980-01-01"}).status_code == 200
    assert config.AGE_IP_LOCK_AFTER >= 10
    ratelimit.reset()


def test_no_teen_code_paths_left():
    import app.community.privacy as p, app.community.identity as i, app.community.catalog as c
    for name in ("is_minor", "clamp_for_minor", "migrate_minors"):
        assert not hasattr(p, name)
    assert not hasattr(identity.Actor, "is_teen") and not hasattr(c, "viewer_sees_no_counts") and not hasattr(c, "audience_ok")
    for name in ("ADULT_AGE", "TEEN_PUBLIC_ENABLED", "TEEN_FOLLOWERS_ENABLED", "HIDE_COUNTS_FOR_MINORS"):
        assert not hasattr(config, name)
    me = client(ADULT).get("/api/me").json()
    assert "age_group" not in me and me["send"]["role"] == "adult"


def test_wording_is_18_plus_with_no_kids_teen_or_coppa_language_and_legal_text_is_marked_draft():
    for f in ("terms.html", "privacy.html", "COMMUNITY_GUIDELINES.html", "COMMUNITY_GUIDELINES.md"):
        t = (config.STATIC / f).read_text()
        low = t.lower()
        assert "18" in t and "draft, pending legal review" in low, f
        for w in ("kids", "teen", "coppa", "grown-up", "13 and up", "13+"):
            assert w not in low, (f, w)
    readme = (config.STATIC.parent / "README.md").read_text().lower()
    assert "18+ only" in readme and "coppa" not in readme and " teen" not in readme
    for f in ("index.html", "community.js", "send.js"):
        low = (config.STATIC / f).read_text().lower()
        assert "teen" not in low and "kids" not in low and "grown-up" not in low, f
    assert 'value="underage_user"' in (config.STATIC / "index.html").read_text()


def publish(c, bid, vis="public", title="Lamp"):
    return c.post("/api/showcase", json={"build_id": bid, "title": title, "accept_guidelines": True, "visibility": vis})


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


def test_legacy_under_18_account_is_restricted_not_deleted():
    USERS.update(lambda d: d.__setitem__("legacy-young-sid-000000", {"id": "ly1", "display_name": "Old", "dob": "2012-02-02", "links": {}, "following": [],
                                                                    "privacy": {"profile": "public", "social": "on", "default_visibility": "public"}}))
    u = USERS.read()["legacy-young-sid-000000"]
    assert identity.restricted(u) and privacy.effective("public", u) == "private"
    assert "legacy-young-sid-000000" in USERS.read()
