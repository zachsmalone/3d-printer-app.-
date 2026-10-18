"""DMCA legal compliance (Phase 1 Task 5): public legal routes, formal notice intake,
repeat-infringer tracking. The designated-agent registration itself ($6, copyright.gov) is a
real-world step for Zach — the code records notices and counts strikes."""
import json

import pytest

from app.community import moderation
from app.community.store import MODERATION, USERS
from tests.b1 import client, ADMIN

ROOT = __file__


def U(n="Maker", dob="1990-01-01"):
    return client({"display_name": n, "dob": dob})


def publish(c, title="Pub"):
    from tests.b1 import photo_build
    r = c.post("/api/showcase", json={"build_id": photo_build(c), "title": title, "description": "d",
                                      "tags": ["calib"], "accept_guidelines": True, "nsfw": False,
                                      "visibility": "public"})
    assert r.status_code == 200, r.text
    return r.json()


NOTICE = {"reporter_name": "Ann Author", "reporter_contact": "ann@example.org",
          "original_work": "My lamp shade design, 2024", "item_ref": "https://zeim.example.org/showcase/ITEM",
          "good_faith": True, "accuracy": True, "signature": True}


@pytest.fixture(autouse=True)
def _clean():
    yield
    MODERATION.write({"hidden": [], "reports": []})


def test_legal_routes_serve_the_pages():
    for path, needle in (("/legal/terms", "dmca"), ("/legal/privacy", "privacy"),
                         ("/legal/community-guidelines", "rules"), ("/legal/takedown", "dmca")):
        r = client().get(path)
        assert r.status_code == 200 and needle in r.text.lower(), (path, needle)


def test_legal_terms_injects_the_configured_takedown_contact(monkeypatch):
    from app.services import credits
    monkeypatch.setattr(credits, "data", lambda: {"takedown": {"contact": "dmca@zeim.test"}})
    r = client().get("/legal/terms")
    assert "[COPYRIGHT CONTACT TO BE ADDED]" not in r.text
    assert "dmca@zeim.test" in r.text


def test_dmca_notice_intake_requires_the_formal_elements():
    a = U("DmcaA"); it = publish(a)
    notice = dict(NOTICE, item_ref=it["id"])
    for missing in ("reporter_name", "reporter_contact", "original_work", "item_ref"):
        bad = {k: v for k, v in notice.items() if k != missing}
        assert client().post("/api/report/takedown", json=bad).status_code == 422
    bad = dict(notice); bad["good_faith"] = False
    assert client().post("/api/report/takedown", json=bad).status_code == 422


def test_dmca_notice_lands_in_the_admin_queue_with_metadata():
    a = U("DmcaB"); it = publish(a)
    r = client().post("/api/report/takedown", json=dict(NOTICE, item_ref=f"https://zeim.test/showcase/{it['id']}"))
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["status"] == "open"
    row = next(x for x in MODERATION.read()["reports"] if x["id"] == rep["report_id"])
    assert row["reason"] == "copyright" and row["dmca"]["reporter_contact"] == "ann@example.org"
    # the admin queue shows it (reporter session id never leaked)
    q = client().get("/api/moderation/queue", headers=ADMIN).json()["reports"]
    assert any(x["id"] == rep["report_id"] and "reporter" not in x for x in q)


def test_three_actioned_dmca_reports_flag_a_repeat_infringer_without_suspending():
    owner = U("DmcaC")
    uid = next(u["id"] for u in USERS.read().values() if u.get("display_name") == "DmcaC")
    ids = [publish(owner, f"P{i}")["id"] for i in range(3)]
    for iid in ids:
        client().post("/api/report/takedown", json=dict(NOTICE, item_ref=iid))
    q = client().get("/api/moderation/queue", headers=ADMIN).json()["reports"]
    for row in [x for x in q if x["item_id"] in ids]:
        client().post(f"/api/moderation/{row['id']}/resolve", json={"action": "remove"}, headers=ADMIN)
    u = next(u for u in USERS.read().values() if u.get("id") == uid)
    assert u.get("repeat_infringer") is True            # flagged
    assert not u.get("suspended")                        # but never auto-suspended: an admin decides that
    # two strikes alone do not flag
    owner2 = U("DmcaD")
    uid2 = next(u["id"] for u in USERS.read().values() if u.get("display_name") == "DmcaD")
    ids2 = [publish(owner2, f"Q{i}")["id"] for i in range(2)]
    for iid in ids2:
        client().post("/api/report/takedown", json=dict(NOTICE, item_ref=iid))
    q = client().get("/api/moderation/queue", headers=ADMIN).json()["reports"]
    for row in [x for x in q if x["item_id"] in ids2]:
        client().post(f"/api/moderation/{row['id']}/resolve", json={"action": "remove"}, headers=ADMIN)
    u2 = next(u for u in USERS.read().values() if u.get("id") == uid2)
    assert not u2.get("repeat_infringer")
    assert moderation.copyright_strikes(uid2) == 2
