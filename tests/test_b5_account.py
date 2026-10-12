"""Small batch after Batch B: sign out (server side) and the recovery-code way back in."""
from tests.b1 import client, ADULT, TEEN


def test_sign_out_gives_this_browser_a_new_empty_session_and_keeps_the_account():
    c = client(ADULT)
    me = c.get("/api/me").json(); assert me["signed_up"]
    old = c.cookies.get("p3d_sid")
    r = c.post("/api/me/signout"); assert r.status_code == 200 and r.json() == {"signed_out": True}
    assert c.cookies.get("p3d_sid") != old
    assert c.get("/api/me").json()["signed_up"] is False
    assert c.post("/api/me/signout").status_code == 400                   # nothing to sign out of
    from app.community.store import USERS
    assert any(u.get("id") == me["id"] for u in USERS.read().values())     # the account still exists on the server


def test_an_adult_gets_back_in_with_the_recovery_code_and_the_code_changes():
    c = client(ADULT)
    username = c.get("/api/me").json()["username"]
    code = c.post("/api/me/recovery-code").json()["recovery_code"]
    c.post("/api/me/signout")
    r = c.post("/api/me/recover", json={"code": code}); assert r.status_code == 200, r.text
    assert r.json()["username"] == username and r.json()["recovery_code"] != code
    assert c.get("/api/me").json()["signed_up"] is True
    c.post("/api/me/signout")
    assert c.post("/api/me/recover", json={"code": code}).status_code == 404        # the old code is single-use


def test_a_teen_can_sign_out_too_and_has_no_recovery_code():
    t = client(TEEN)
    assert t.post("/api/me/recovery-code").status_code == 403
    assert t.post("/api/me/signout").status_code == 200 and t.get("/api/me").json()["signed_up"] is False
