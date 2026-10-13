"""ZEIM Originals proof badges: Simulated by default, Test-printed only with a logged real print (admin), the badge names
the printer that was logged (never an invented 'K1-tested'), wrong entries are retracted, not deleted."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.community import originals_proof as op

ADMIN = {"X-Admin-Token": "t0k"}
c = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_log():
    op.PRINTS.write({"prints": []})
    yield
    op.PRINTS.write({"prints": []})


def originals():
    return [i for i in c.get("/api/showcase?tab=free").json()["items"] if i["original"]]


def item(iid):
    return next(i for i in originals() if i["id"] == iid)


def log(iid, **kw):
    body = {"printer": "Creality K1", "printed_on": date.today().isoformat(), "result": "printed", **kw}
    return c.post(f"/api/moderation/originals/{iid}/prints", json=body, headers=ADMIN)


def test_every_original_defaults_to_simulated_and_says_computer_only():
    o = originals()
    assert o
    for i in o:
        assert i["proof"]["badge"] == "simulated" and i["proof"]["label"] == "Simulated", i["id"]
        assert "computer only" in i["proof"]["detail"] and "Untested print" in i["proof"]["detail"]
        assert "K1" not in i["proof"]["detail"] and i["untested"] is True
    n = c.get("/api/showcase?tab=free").json()["originals_notice"]
    assert "None has been test-printed yet" in n and "untested print" in n


def test_only_the_admin_can_log_a_print_and_only_for_an_original():
    iid = originals()[0]["id"]
    assert c.post(f"/api/moderation/originals/{iid}/prints", json={"printer": "Creality K1", "printed_on": "2026-10-01",
                  "result": "worked"}).status_code == 403
    assert c.post(f"/api/moderation/originals/{iid}/prints", json={"printer": "Creality K1", "printed_on": "2026-10-01",
                  "result": "worked"}, headers={"X-Admin-Token": "nope"}).status_code == 403
    assert log("not-an-original").status_code == 404
    assert item(iid)["proof"]["badge"] == "simulated"


@pytest.mark.parametrize("bad", [
    {"printer": ""},
    {"printed_on": (date.today() + timedelta(days=2)).isoformat()},
    {"printed_on": "yesterday"},
    {"result": "probably fine"},
])
def test_log_needs_printer_real_date_and_known_result(bad):
    iid = originals()[0]["id"]
    r = log(iid, **bad)
    assert r.status_code == 400, r.text
    assert item(iid)["proof"]["badge"] == "simulated"


def test_logged_print_shows_test_printed_naming_only_the_logged_printer():
    o = originals(); iid, other = o[0]["id"], o[1]["id"]
    r = log(iid, printer="Creality K1", result="printed")
    assert r.status_code == 200, r.text
    i = item(iid)
    assert i["proof"]["badge"] == "test_printed" and i["proof"]["label"] == "Test-printed" and i["untested"] is False
    assert "Creality K1" in i["proof"]["detail"] and "not checked yet" in i["proof"]["detail"]
    assert item(other)["proof"]["badge"] == "simulated" and "K1" not in item(other)["proof"]["detail"]
    assert "1 has been test-printed" in c.get("/api/showcase?tab=free").json()["originals_notice"]
    log(iid, printer="Prusa MK4", result="worked")
    d = item(iid)["proof"]["detail"]
    assert "worked as intended" in d


def test_a_failed_print_alone_keeps_simulated_and_says_so():
    iid = originals()[0]["id"]
    assert log(iid, result="failed").status_code == 200
    p = item(iid)["proof"]
    assert p["badge"] == "simulated" and "failed" in p["detail"]


def test_retract_keeps_the_entry_and_returns_to_simulated():
    iid = originals()[0]["id"]
    e = log(iid).json()["entry"]
    r = c.post(f"/api/moderation/originals/prints/{e['id']}/retract", json={"reason": "logged on the wrong item"}, headers=ADMIN)
    assert r.status_code == 200 and r.json()["proof"]["badge"] == "simulated"
    lst = c.get("/api/moderation/originals/prints", headers=ADMIN).json()["prints"]
    assert [x["id"] for x in lst] == [e["id"]] and lst[0]["retracted"]["reason"] == "logged on the wrong item"
    assert c.post("/api/moderation/originals/prints/tp_missing/retract", json={}, headers=ADMIN).status_code == 404
    assert c.get("/api/moderation/originals/prints").status_code == 403


def test_user_projects_carry_no_proof_badge():
    for i in c.get("/api/showcase?tab=free").json()["items"]:
        if not i["original"]:
            assert i["proof"] is None
