"""Change requests CR-5 (photo permission), CR-11 (moderation basics), CR-15 (adult recovery code).
(CR-2/3/4 classroom tests removed with school features, 2026-10-12.)"""
import json, os, re
import pytest
from app import config

from app.services.history import store
from tests import b1
from tests.b1 import client, gen, photo_build, ADULT, SUSPENDED, UNDER18, ADMIN


def owned(sid):
    return [m["id"] for m in store.list(sid)]


def sid_of(c):
    return c.cookies.get("p3d_sid")


# ------------------------------------------------------------------------------------------------ CR-2



# ------------------------------------------------------------------------------------------------ CR-3



# ------------------------------------------------------------------------------------------------ CR-4



# ------------------------------------------------------------------------------------------------ CR-5
@pytest.fixture
def ack_on(monkeypatch):
    monkeypatch.setattr(config, "PHOTO_ACK_REQUIRED", True)


def other_png():
    """A photo that is NOT ZEIM's built-in sample image (static/sample.jpg is exempt)."""
    import io
    from PIL import Image
    b = io.BytesIO(); Image.effect_mandelbrot((96, 96), (-2, -1.5, 1, 1.5), 40).convert("RGB").save(b, "PNG"); return b.getvalue()


SAMPLE_PNG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "sample.jpg")


def test_cr5_studio_build_from_an_uploaded_photo_needs_the_box_and_records_it(ack_on):
    c = client()
    r = gen(c, ack=False, data=other_png()); assert r.status_code == 400 and "permission" in r.json()["detail"] and "photo" in r.json()["detail"].lower()
    assert store.list(sid_of(c)) == []                                   # nothing was built, no history slot used
    r = gen(c, ack=True, data=other_png()); assert r.status_code == 200, r.text
    assert store.get(r.json()["id"])["photo_ack"] is True          # store.get works in json and db modes


def test_cr5_built_in_sample_needs_no_box_and_is_recorded_as_sample(ack_on):
    c = client()
    r = gen(c, ack=False, name="sample.png", data=open(SAMPLE_PNG, "rb").read()); assert r.status_code == 200, r.text
    assert store.get(r.json()["id"])["photo_ack"] == "sample"
    # the exemption is the exact file, not the file name
    r = gen(c, ack=False, name="sample.png", data=other_png()); assert r.status_code == 400


def test_cr5_edit_photo_needs_the_box_but_a_3d_file_and_the_sample_do_not(ack_on):
    c = client()
    img = other_png()
    r = c.post("/api/edit/new", files={"file": ("p.png", img, "image/png")}); assert r.status_code in (400, 415) and "permission" in r.json()["detail"]
    r = c.post("/api/edit/new", files={"file": ("p.png", img, "image/png")}, data={"photo_ack": "true"}); assert r.status_code == 200, r.text
    assert json.loads((store.dir(r.json()["id"]) / "meta.json").read_text())["photo_ack"] is True
    r = c.post("/api/edit/new", files={"file": ("sample.png", open(SAMPLE_PNG, "rb").read(), "image/png")}); assert r.status_code == 200, r.text
    assert json.loads((store.dir(r.json()["id"]) / "meta.json").read_text())["photo_ack"] == "sample"
    r = c.post("/api/edit/new", files={"file": ("cube.stl", b1.box_stl(), "model/stl")}); assert r.status_code == 200, r.text    # a 3D file is not a photo
    assert "photo_ack" not in json.loads((store.dir(r.json()["id"]) / "meta.json").read_text())



# ------------------------------------------------------------------------------------------------ CR-11
def _item_for_reports():
    pub = client(ADULT); bid = photo_build(pub)
    r = pub.post("/api/showcase", json={"build_id": bid, "title": "Reportable", "description": "a thing", "tags": [], "accept_guidelines": True, "nsfw": False, "visibility": "public"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_cr11_duplicate_report_returns_the_existing_id_and_other_reasons_or_people_are_separate():
    iid = _item_for_reports()
    a, b = client(), client()
    r1 = a.post(f"/api/showcase/{iid}/report", json={"reason": "other", "details": "x"}).json()
    r2 = a.post(f"/api/showcase/{iid}/report", json={"reason": "other", "details": "again"}).json()
    assert r2["id"] == r1["id"] and r2.get("duplicate") is True
    assert a.post(f"/api/showcase/{iid}/report", json={"reason": "copyright"}).json()["id"] != r1["id"]
    assert b.post(f"/api/showcase/{iid}/report", json={"reason": "other"}).json()["id"] != r1["id"]
    q = client().get("/api/moderation/queue", headers=ADMIN).json()["reports"]
    assert len([x for x in q if x["item_id"] == iid]) == 3


def test_cr11_the_eleventh_report_in_a_minute_is_refused():
    iid = _item_for_reports()
    c = client()
    codes = [c.post(f"/api/showcase/{iid}/report", json={"reason": "other"}).status_code for _ in range(11)]
    assert codes[:10] == [200] * 10 and codes[10] == 429
    assert "report" in client().get("/api/moderation/queue", headers=ADMIN).text


def test_cr11_only_minor_safety_auto_hides_and_many_ordinary_reports_never_do():
    iid = _item_for_reports()
    for _ in range(6):
        assert client().post(f"/api/showcase/{iid}/report", json={"reason": "other"}).status_code == 200
    assert client().get(f"/api/showcase/{iid}").status_code == 200                       # six people: still visible (CR-11 f)
    r = client().post(f"/api/showcase/{iid}/report", json={"reason": "minor_safety"}).json(); assert r["auto_hidden"] is True
    assert client().get(f"/api/showcase/{iid}").status_code == 404


def test_cr11_audit_log_lines_for_report_hide_restore_dismiss(caplog):
    import logging
    iid = _item_for_reports()
    with caplog.at_level(logging.INFO, logger="zeim.audit"):
        rid = client().post(f"/api/showcase/{iid}/report", json={"reason": "other"}).json()["id"]
        for act in ("hide", "restore", "dismiss"):
            assert client().post(f"/api/moderation/{rid}/resolve", json={"action": act}, headers=ADMIN).status_code == 200
    text = "\n".join(r.getMessage() for r in caplog.records)
    for word in ("moderation report:", "moderation hide:", "moderation restore:", "moderation dismiss:"):
        assert word in text, text
    assert f"report={rid}" in text and "reporter=" in text and "at=" in text


def test_cr11_admin_page_and_queue_are_token_protected_oldest_first_with_previews_and_age():
    iid = _item_for_reports(); iid2 = _item_for_reports()
    c = client()
    c.post(f"/api/showcase/{iid}/report", json={"reason": "other"}); c.post(f"/api/showcase/{iid2}/report", json={"reason": "copyright"})
    page = client().get("/admin/moderation"); assert page.status_code == 200 and "Admin token" in page.text and "noindex" in page.text
    assert "X-Admin-Token" in open(os.path.join(os.path.dirname(SAMPLE_PNG), "moderation.js")).read()
    assert client().get("/api/moderation/queue").status_code == 403
    assert client().get("/api/moderation/queue", headers={"X-Admin-Token": "wrong"}).status_code == 403
    q = client().get("/api/moderation/queue", headers=ADMIN).json()
    ids = [r["item_id"] for r in q["reports"] if r["item_id"] in (iid, iid2)]
    assert ids == [iid, iid2] and isinstance(q["oldest_open_age_s"], int) and q["oldest_open_age_s"] >= 0
    assert all("reporter" not in r for r in q["reports"]) and q["reports"][0]["preview"]["title"]
    for _ in range(config.ADMIN_FAIL_LIMIT):
        client().get("/api/moderation/queue", headers={"X-Admin-Token": "nope"})
    assert client().get("/api/moderation/queue", headers=ADMIN).status_code in (429, 200)       # (same limiter the other admin routes use)



# ------------------------------------------------------------------------------------------------ CR-15
def _adult_with_code():
    t = client(); r = t.post("/api/me/signup", json=ADULT); assert r.status_code == 200, r.text
    return t, r.json()["recovery_code"], None


def test_cr15_adult_signup_shows_a_recovery_code_once_and_stores_only_a_hash():
    t, code, room = _adult_with_code()
    assert re.fullmatch(r"[A-Z2-9]{4}(-[A-Z2-9]{4}){3}", code)
    from app.community.store import USERS
    stored = json.dumps(USERS.read())
    assert code not in stored and code.replace("-", "") not in stored and "recovery" in stored       # only the hash is there
    assert "recovery_code" not in t.get("/api/me").json()
    assert t.get("/api/me").json()["recovery"]["has_code"] is True
    young = client(); r = young.post("/api/me/signup", json=UNDER18); assert r.status_code == 403 and "recovery_code" not in r.json()   # under 18: no account at all


def test_cr15_new_browser_regains_the_adult_account_and_the_old_one_loses_it():
    t, code, room = _adult_with_code()
    old_sid = sid_of(t)
    bid = photo_build(t)
    new = client()
    assert new.post("/api/me/recover", json={"code": "AAAA-BBBB-CCCC-DDDD"}).status_code == 404
    r = new.post("/api/me/recover", json={"code": code.lower()}); assert r.status_code == 200, r.text
    assert r.json()["signed_up"] and r.json()["display_name"] == ADULT["display_name"] and r.json()["recovery_code"] != code
    assert owned(sid_of(new)) == [bid] and owned(old_sid) == []
    # the old browser lost the account
    assert t.get("/api/me").json()["signed_up"] is False
    # the used code is dead, the new one works (once more, from yet another browser)
    assert client().post("/api/me/recover", json={"code": code}).status_code == 404
    again = client().post("/api/me/recover", json={"code": r.json()["recovery_code"]}); assert again.status_code == 200
    assert new.get("/api/me").json()["signed_up"] is False


def test_cr15_regenerate_kills_the_old_code_and_wrong_guesses_are_rate_limited():
    t, code, room = _adult_with_code()
    fresh = t.post("/api/me/recovery-code"); assert fresh.status_code == 200
    assert client().post("/api/me/recover", json={"code": code}).status_code == 404
    c = client()
    for _ in range(config.RECOVERY_FAIL_LIMIT):
        assert c.post("/api/me/recover", json={"code": "ZZZZ-ZZZZ-ZZZZ-ZZZZ"}).status_code == 404
    assert c.post("/api/me/recover", json={"code": fresh.json()["recovery_code"]}).status_code == 429      # even the right code waits
    assert client().post("/api/me/recovery-code").status_code == 403                                      # no account, no code


def test_cr15_cannot_take_over_into_a_browser_that_already_has_an_account():
    t, code, room = _adult_with_code()
    other = client(SUSPENDED)
    assert other.post("/api/me/recover", json={"code": code}).status_code == 409


# ---- Edge 3: a file name never becomes a title ----------------------------------------------------------------------------------
def test_upload_file_name_never_becomes_the_build_title():
    import io as _io
    png = other_png(); box_stl = b1.box_stl
    c = client(ADULT)
    r = c.post("/api/generate", files={"file": ("IMG_2231_MiaJohnson.png", _io.BytesIO(png), "image/png")}, data={"mode": "relief", "photo_ack": "true"})
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "My photo build" and ("MiaJohnson" in r.text) is False
    r = c.post("/api/edit/new", files={"file": ("MiaJohnson_Lincoln.stl", box_stl(), "application/octet-stream")}); assert r.status_code == 200, r.text
    assert r.json()["title"] == "My model" and ("MiaJohnson" in r.text) is False
    r = c.post("/api/edit/new", files={"file": ("IMG_MiaJohnson.png", _io.BytesIO(png), "image/png")}, data={"photo_ack": "true"}); assert r.status_code == 200, r.text
    assert r.json()["title"] == "My photo build" and ("MiaJohnson" in r.text) is False
    r = c.post("/api/generate", files={"file": ("MiaJohnson.png", _io.BytesIO(png), "image/png")}, data={"mode": "relief", "title": "Desk fox", "photo_ack": "true"})
    assert r.json()["title"] == "Desk fox"                                   # the person's own typing still works


def test_chunked_json_body_is_capped_before_parsing_and_small_chunked_bodies_still_work():
    from app.api.textcap import MAX_JSON_BODY
    c = client(ADULT)
    def big():
        for _ in range(MAX_JSON_BODY // 65536 + 3):
            yield b" " * 65536
    r = c.post("/api/me/signup", content=big(), headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    def small():
        yield b'{"display_name": "Ada",'
        yield b' "dob": "1985-05-05"}'
    r = client().post("/api/me/signup", content=small(), headers={"Content-Type": "application/json"})
    assert r.status_code == 200, r.text


def test_data_files_are_private_600_and_data_dirs_700(tmp_path, monkeypatch):
    import stat
    from app import config
    from app.community import store as st
    c = client(); c.post("/api/me/signup", json={"display_name": "Ada", "dob": "1985-05-05"})
    p = st.USERS.path
    assert p.exists() and stat.S_IMODE(p.stat().st_mode) == 0o600
    p.chmod(0o644)                                            # a file left over from an older version
    monkeypatch.setattr(config, "DATA", p.parent)
    assert config.harden_data_permissions() >= 1 and stat.S_IMODE(p.stat().st_mode) == 0o600
    assert stat.S_IMODE(p.parent.stat().st_mode) == 0o700


def test_s01_local_mode_settings_refuse_a_cross_site_origin(monkeypatch):
    monkeypatch.setattr(config, "MODE", "local")
    c = client(ADULT)
    h = {"host": "127.0.0.1:8765"}
    ok = c.put("/api/settings", json={"printers": []}, headers=h)
    # TestClient's peer is not loopback, so what matters here is the origin rule on the owner path:
    from app.api import guards
    from starlette.requests import Request
    def req(origin):
        hd = [(b"host", b"127.0.0.1:8765")] + ([(b"origin", origin.encode())] if origin else [])
        return Request({"type": "http", "headers": hd, "client": ("127.0.0.1", 5), "method": "PUT", "path": "/", "query_string": b""})
    from fastapi import HTTPException
    guards.require_settings_admin(req(None), type("A", (), {"sid": "x"})())                           # no Origin (curl, same-origin GET-less) fine
    guards.require_settings_admin(req("http://127.0.0.1:8765"), type("A", (), {"sid": "x"})())        # ZEIM's own page
    for bad in ("https://evil.example", "null"):
        with pytest.raises(HTTPException) as e:
            guards.require_settings_admin(req(bad), type("A", (), {"sid": "x"})())
        assert e.value.status_code == 403


def test_built_in_samples_get_a_friendly_title_but_never_from_a_file_name():
    c = client(ADULT)
    assert gen(c, data=open(SAMPLE_PNG, "rb").read()).json()["title"] == "Sample photo"                      # ZEIM's own sample.jpg
    stl = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "sample_model.stl"), "rb").read()
    r = c.post("/api/edit/new", files={"file": ("whatever_name.stl", stl, "application/octet-stream")}); assert r.json()["title"] == "Sample model"
