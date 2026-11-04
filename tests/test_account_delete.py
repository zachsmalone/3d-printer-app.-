"""Self-serve 'Delete my account': confirm required, login stops at once, the in-app purge removes the data."""
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.community import account_delete
from app.community.store import FAVORITES, LISTINGS, PREFS, USERS


def _signed_up(name="Deleter"):
    c = TestClient(app)
    assert c.post("/api/me/signup", json={"display_name": name}).status_code == 200
    return c


def test_needs_confirm_and_sign_in():
    assert TestClient(app).post("/api/me/delete-account", json={"confirm": "DELETE"}).status_code == 400
    c = _signed_up()
    assert c.post("/api/me/delete-account", json={}).status_code == 400
    assert c.get("/api/me").json()["signed_up"] is True


def test_marks_signs_out_and_purge_removes_everything():
    c = _signed_up("Gone Soon")
    sid = c.cookies.get("p3d_sid")
    code = c.post("/api/me/recovery-code").json()["recovery_code"]
    FAVORITES.update(lambda d: d.__setitem__(sid, ["x1"]))
    PREFS.update(lambda d: d.__setitem__(sid, {"a": 1}))
    LISTINGS.update(lambda l: l.append({"id": "pdel_test1", "owner_sid": sid, "title": "t"}))
    r = c.post("/api/me/delete-account", json={"confirm": "DELETE"})
    assert r.status_code == 200 and r.json()["deletion_requested"] is True
    assert USERS.read()[sid].get("delete_requested_at")
    assert c.get("/api/me").json()["signed_up"] is False           # this browser got a fresh empty session
    other = TestClient(app)
    assert other.post("/api/me/recover", json={"code": code}).status_code == 404   # can't be recovered meanwhile
    assert account_delete.purge_due() >= 1
    assert sid not in USERS.read() and sid not in FAVORITES.read() and sid not in PREFS.read()
    assert not any(i.get("owner_sid") == sid for i in LISTINGS.read())


def test_purge_runs_in_process_and_privacy_says_7_days():
    src = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text()
    assert "account_delete.start_background(app)" in src
    p = (Path(__file__).resolve().parents[1] / "static" / "privacy.html").read_text()
    assert "within 7 days" in p and "no self-serve account deletion" not in p


def test_password_account_cannot_sign_in_after_delete_and_login_row_is_purged():
    H = {"X-Requested-With": "zeim"}
    c = TestClient(app)
    r = c.post("/api/auth/password/register", headers=H, json={"display_name": "Pw Del", "username": "pwdel1",
                                                                "password": "Correct-Horse-9x!"})
    assert r.status_code == 201
    assert c.post("/api/me/delete-account", json={"confirm": "DELETE"}).status_code == 200
    login = lambda: TestClient(app).post("/api/auth/password/login", headers=H,
                                         json={"identifier": "pwdel1", "password": "Correct-Horse-9x!"}).status_code
    assert login() != 200
    account_delete.purge_due(app.state.auth_service)
    svc = app.state.auth_service
    assert svc.store.one("SELECT id FROM accounts WHERE login_name='pwdel1'") is None
    assert login() != 200
