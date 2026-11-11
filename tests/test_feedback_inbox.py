"""Private Feedback inbox: owner/admin only, real NPS math, stored notes only."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from tests.b1 import ADMIN, ADULT, client as make_client
from app import config
from app.community import feedback_inbox
from app.community.store import USERS


def _shared(monkeypatch):
    """This suite defaults to local mode (TestClient counts as the machine owner). Shared is how zeimapp.com runs."""
    monkeypatch.setattr(config, "MODE", "shared")


def _mark_site_admin(c: TestClient) -> None:
    me = c.get("/api/me").json()
    uid = me["id"]

    def flag(d):
        for u in d.values():
            if u.get("id") == uid:
                u["site_admin"] = True

    USERS.update(flag)


def test_anonymous_and_plain_account_are_denied(monkeypatch):
    _shared(monkeypatch)
    c = make_client()
    assert c.get("/api/feedback/inbox").status_code == 404
    assert c.get("/feedback").status_code == 404
    assert c.get("/api/me").json()["feedback_view"] is False

    signed = make_client(ADULT)
    assert signed.get("/api/me").json()["signed_up"] is True
    assert signed.get("/api/me").json()["feedback_view"] is False
    assert signed.get("/api/feedback/inbox").status_code == 404
    assert signed.get("/feedback").status_code == 404


def test_site_admin_account_can_open_inbox(monkeypatch):
    _shared(monkeypatch)
    c = make_client(ADULT)
    assert c.get("/api/feedback/inbox").status_code == 404
    _mark_site_admin(c)
    me = c.get("/api/me").json()
    assert me["feedback_view"] is True
    r = c.get("/api/feedback/inbox")
    assert r.status_code == 200
    body = r.json()
    assert "nps" in body and "scores" in body and "notes" in body
    assert set(body["nps"]) == {"answers", "promoters", "passives", "detractors", "score"}
    assert body["nps"]["answers"] == body["nps"]["promoters"] + body["nps"]["passives"] + body["nps"]["detractors"]
    assert body["scores"]["total"] == body["nps"]["answers"]
    page = c.get("/feedback", follow_redirects=False)
    assert page.status_code == 303
    assert page.headers["location"] == "/#feedback"


def test_admin_token_can_open_without_site_admin_flag(monkeypatch):
    _shared(monkeypatch)
    c = make_client()
    assert c.get("/api/feedback/inbox").status_code == 404
    r = c.get("/api/feedback/inbox", headers=ADMIN)
    assert r.status_code == 200
    assert set(r.json()["nps"]) >= {"answers", "promoters", "passives", "detractors", "score"}
    deny = c.get("/api/feedback/inbox", headers={"X-Admin-Token": "not-the-token"})
    assert deny.status_code == 404


def test_local_owner_can_open_inbox():
    """Local mode + this computer (the test client, via conftest) is the existing owner check."""
    c = make_client()
    assert c.get("/api/me").json()["feedback_view"] is True
    assert c.get("/api/feedback/inbox").status_code == 200
    page = c.get("/feedback", follow_redirects=False)
    assert page.status_code == 303


def test_nps_summary_math_and_note_list(tmp_path, monkeypatch):
    _shared(monkeypatch)
    monkeypatch.setattr(config, "DATA", tmp_path)
    (tmp_path / "metrics").mkdir()
    # 10 and 9 are promoters, 7 is passive, 3 and 0 are detractors.
    # NPS = (2/5 promoters - 2/5 detractors) * 100 = 0.
    lines = [
        {"d": "2026-11-01", "e": "nps", "s": 10},
        {"d": "2026-11-02", "e": "nps", "s": 9},
        {"d": "2026-11-03", "e": "nps", "s": 7},
        {"d": "2026-11-03", "e": "nps", "s": 3},
        {"d": "2026-11-04", "e": "nps", "s": 0},
        {"d": "2026-11-04", "e": "first_print", "b": "1-5m"},
        "not-json",
        {"d": "2026-11-04", "e": "nps", "s": True},
    ]
    (tmp_path / "metrics" / "2026-11.jsonl").write_text(
        "".join((json.dumps(x) if not isinstance(x, str) else x) + "\n" for x in lines),
        encoding="utf-8",
    )
    summary = feedback_inbox.nps_summary()
    assert summary == {"answers": 5, "promoters": 2, "passives": 1, "detractors": 2, "score": 0}
    # 3 promoters, 1 passive, 2 detractors out of 6 -> round(100 * (3-2)/6) = 17
    extra = tmp_path / "metrics" / "2026-10.jsonl"
    extra.write_text(json.dumps({"d": "2026-10-31", "e": "nps", "s": 9}) + "\n", encoding="utf-8")
    assert feedback_inbox.nps_summary()["score"] == 17
    assert feedback_inbox.nps_summary()["answers"] == 6

    notes = tmp_path / "feedback"
    notes.mkdir()
    (notes / "aaa.json").write_text(json.dumps({
        "at": 1000, "who": "guest", "text": "<script>alert(1)</script>", "emailed": False,
    }), encoding="utf-8")
    (notes / "bbb.json").write_text(json.dumps({
        "at": 2000, "who": "Ada", "text": "Please add a dark bed.", "emailed": True,
    }), encoding="utf-8")
    inbox = feedback_inbox.inbox(notes_limit=1, scores_limit=2)
    assert inbox["nps"]["answers"] == 6
    assert inbox["scores"]["total"] == 6 and len(inbox["scores"]["items"]) == 2
    assert inbox["scores"]["items"][0]["date"] >= inbox["scores"]["items"][1]["date"]
    assert inbox["notes"]["total"] == 2 and len(inbox["notes"]["items"]) == 1
    assert inbox["notes"]["items"][0]["who"] == "Ada"
    assert inbox["notes"]["items"][0]["text"] == "Please add a dark bed."
    page2 = feedback_inbox.inbox(notes_offset=1, notes_limit=1)
    assert page2["notes"]["items"][0]["text"] == "<script>alert(1)</script>"  # raw stored text; the page uses textContent
    assert page2["notes"]["items"][0]["emailed"] is False

    c = make_client()
    r = c.get("/api/feedback/inbox", headers=ADMIN)
    assert r.status_code == 200
    assert r.json()["nps"]["answers"] == 6
    assert r.json()["nps"]["score"] == 17
    assert r.json()["notes"]["total"] == 2


def test_known_nps_examples():
    assert feedback_inbox.nps_summary([]) == {
        "answers": 0, "promoters": 0, "passives": 0, "detractors": 0, "score": None,
    }
    rows = [{"date": "2026-01-01", "score": s} for s in (10, 9, 3)]
    # 2 promoters, 0 passives, 1 detractor of 3 -> (66.7-33.3) = 33
    assert feedback_inbox.nps_summary(rows) == {
        "answers": 3, "promoters": 2, "passives": 0, "detractors": 1, "score": 33,
    }
