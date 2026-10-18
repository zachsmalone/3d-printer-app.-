"""Moderation workflow (Phase 1 Task 6/7): appeals, persistent audit trail, IP/UA capture,
secure preservation and NCMEC escalation (records only — nothing is ever auto-submitted)."""
import io, json, os, stat

import pytest

from app.community import moderation
from app.community.store import MODERATION
from app.config import DATA
from tests.b1 import client, ADMIN

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def U(n="Maker", dob="1990-01-01"):
    return client({"display_name": n, "dob": dob})


_MINE = set()          # showcase items created by this file (removed again on teardown)


def publish(c, title="Pub", **extra):
    from tests.b1 import photo_build
    r = c.post("/api/showcase", json={"build_id": photo_build(c), "title": title, "description": "d",
                                      "tags": ["calib"], "accept_guidelines": True, "nsfw": False,
                                      "visibility": "public", **extra})
    assert r.status_code == 200, r.text
    _MINE.add(r.json()["id"])
    return r.json()


@pytest.fixture(autouse=True)
def _clean_moderation():
    yield
    MODERATION.write({"hidden": [], "reports": []})
    from app.community.store import LISTINGS
    LISTINGS.update(lambda l: [i for i in l if i["id"] not in _MINE])
    _MINE.clear()


# ---------------- report context (Task 7: IP / user agent / timestamp) ----------------

def test_report_records_ip_and_user_agent():
    a = U("RepA"); it = publish(a)
    v = U("RepV")
    r = v.post(f"/api/showcase/{it['id']}/report", json={"reason": "copyright", "details": "mine"},
               headers={"X-Forwarded-For": "203.0.113.7", "User-Agent": "Mozilla/5.0 test-agent"})
    assert r.status_code == 200
    rep = next(x for x in MODERATION.read()["reports"] if x["item_id"] == it["id"])
    assert rep["ip"] and rep["user_agent"].startswith("Mozilla") and rep["created"]
    # the public queue view never leaks the reporter's session id (checked separately below)


def test_queue_view_hides_reporter_but_keeps_context_for_admins():
    a = U("RepQ"); it = publish(a)
    U("RepQ2").post(f"/api/showcase/{it['id']}/report", json={"reason": "copyright", "details": "x"})
    q = client().get("/api/moderation/queue", headers=ADMIN).json()["reports"]
    row = next(x for x in q if x["item_id"] == it["id"])
    assert "reporter" not in row and row["ip"] and row["user_agent"]


# ---------------- appeals ----------------

def test_owner_can_appeal_a_decision_and_it_reenters_the_queue():
    a = U("AppA"); it = publish(a)
    U("AppV").post(f"/api/showcase/{it['id']}/report", json={"reason": "copyright", "details": "x"})
    q = client().get("/api/moderation/queue", headers=ADMIN).json()["reports"]
    rid = next(x for x in q if x["item_id"] == it["id"])["id"]
    client().post(f"/api/moderation/{rid}/resolve", json={"action": "remove"}, headers=ADMIN)
    # a stranger cannot appeal someone else's decision
    assert U("AppX").post(f"/api/moderation/appeal/showcase/{it['id']}", json={"text": "unfair"}).status_code == 403
    # the owner can
    r = a.post(f"/api/moderation/appeal/showcase/{it['id']}", json={"text": "it is my own photo"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "appealed" and r.json()["appeal"]["by"]
    # the appealed report is back in the queue and a moderator can re-decide
    q = client().get("/api/moderation/queue", headers=ADMIN).json()["reports"]
    assert any(x["id"] == rid and x["status"] == "appealed" for x in q)
    client().post(f"/api/moderation/{rid}/resolve", json={"action": "restore"}, headers=ADMIN)
    row = next(x for x in MODERATION.read()["reports"] if x["id"] == rid)
    assert row["status"] == "actioned"


def test_appeal_requires_a_decided_report():
    a = U("AppB"); it = publish(a)
    U("AppB2").post(f"/api/showcase/{it['id']}/report", json={"reason": "copyright", "details": "x"})
    r = a.post(f"/api/moderation/appeal/showcase/{it['id']}", json={"text": "why"})
    assert r.status_code == 404          # still open: no decided report to appeal yet


# ---------------- persistent audit trail ----------------

def test_audit_trail_records_every_action():
    a = U("AudA"); it = publish(a)
    U("AudV").post(f"/api/showcase/{it['id']}/report", json={"reason": "copyright", "details": "x"})
    q = client().get("/api/moderation/queue", headers=ADMIN).json()["reports"]
    rid = next(x for x in q if x["item_id"] == it["id"])["id"]
    client().post(f"/api/moderation/{rid}/resolve", json={"action": "dismiss"}, headers=ADMIN)
    trail = client().get("/api/moderation/audit", headers=ADMIN).json()["entries"]
    actions = [e["action"] for e in trail]
    assert "report" in actions and "dismiss" in actions
    assert all("at" in e for e in trail)
    # not without the admin token
    assert client().get("/api/moderation/audit").status_code == 403


# ---------------- preservation + NCMEC escalation (Task 7) ----------------

def test_preserve_then_escalate_ncmec_flow():
    a = U("NcA"); it = publish(a)
    U("NcV").post(f"/api/showcase/{it['id']}/report", json={"reason": "minor_safety", "details": "x"})
    q = client().get("/api/moderation/queue", headers=ADMIN).json()["reports"]
    rid = next(x for x in q if x["item_id"] == it["id"])["id"]
    # escalation REFUSES to run without preserved evidence
    r = client().post(f"/api/moderation/report/{rid}/escalate-ncmec", json={"note": "x"}, headers=ADMIN)
    assert r.status_code == 400 and "Preserve" in r.json()["detail"]
    # preserve: files + context land in a locked directory that no route serves
    p = client().post(f"/api/moderation/report/{rid}/preserve", headers=ADMIN).json()
    d = DATA / "preservation" / rid
    assert (d / "context.json").exists()
    assert json.loads((d / "context.json").read_text())["report"]["reason"] == "minor_safety"
    if p["files"]:
        assert (stat.S_IMODE((d / p["files"][0]).stat().st_mode) & 0o077) == 0     # owner-only
    # now escalation records the decision (and nothing is ever submitted anywhere automatically)
    e = client().post(f"/api/moderation/report/{rid}/escalate-ncmec", json={"note": "suspected CSAM"}, headers=ADMIN).json()
    assert e["status"] == "escalated_ncmec" and e["escalated"]["note"] == "suspected CSAM"
    # the audit trail has both steps
    trail = client().get("/api/moderation/audit", headers=ADMIN).json()["entries"]
    assert {"action"} and [x for x in trail if x["action"] == "preserve"] and [x for x in trail if x["action"] == "escalate_ncmec"]
