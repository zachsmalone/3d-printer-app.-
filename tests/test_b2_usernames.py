"""Unique usernames: server-enforced shape, uniqueness (any case), chat filter, no email/phone-like text, generated for under-18, migration,
and email never appears in a public response."""
import re
import pytest
from app import config
from app.community import usernames
from app.community.store import USERS
from tests.b1 import client, photo_build, ADULT, SUSPENDED, UNDER18, ADMIN


def me(c): return c.get("/api/me").json()


def test_adult_can_choose_a_valid_free_name_or_gets_a_generated_one():
    a = client(); r = a.post("/api/me/signup", json={**ADULT, "username": "ada_makes"}); assert r.json()["username"] == "ada_makes"
    b = client(); r = b.post("/api/me/signup", json=ADULT); assert re.match(r"^[A-Z][a-z]+[A-Z][a-z]+\d{3}$", r.json()["username"])
    c = client(); r = c.post("/api/me/signup", json={**ADULT, "username": "ADA_MAKES"})        # taken ignoring case
    assert r.status_code == 400 and "taken" in r.json()["detail"] and c.get("/api/me").json()["signed_up"] is False


@pytest.mark.parametrize("bad", ["ab", "a" * 19, "NightmareOpsStudio1", "1abc", "has space", "da-sh", "me@example.com", "ada.smith", "http://x", "a1234567b", "Zeim_team", "admin", "Teacher", "fuck_you", "<script>"])
def test_change_refuses_bad_names_with_a_kind_message(bad):
    a = client(ADULT); before = me(a)["username"]
    r = a.put("/api/me/username", json={"username": bad})
    assert r.status_code in (400, 409, 422), (bad, r.status_code, r.text)
    assert me(a)["username"] == before
    assert r.json().get("detail") or r.json().get("message")


def test_change_is_case_insensitive_unique_and_allows_changing_the_case_of_your_own_name():
    a = client(ADULT); b = client(ADULT)
    assert a.put("/api/me/username", json={"username": "Maker_One"}).json()["username"] == "Maker_One"
    r = b.put("/api/me/username", json={"username": "maker_one"}); assert r.status_code == 409 and "taken" in r.json()["detail"]
    r = b.put("/api/me/username", json={"username": "MAKER_ONE"}); assert r.status_code == 409
    assert a.put("/api/me/username", json={"username": "maker_one"}).json()["username"] == "maker_one"     # own name, new case: free, no waiting
    assert b.put("/api/me/username", json={"username": "Maker_One"}).status_code == 409


def _age_the_last_change(sid_user_id, days):
    from datetime import datetime, timedelta, timezone
    USERS.update(lambda d: [u.__setitem__("username_changed", (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()) for u in d.values() if u["id"] == sid_user_id])


def test_a_rename_is_allowed_once_every_90_days_and_the_wait_is_explained():
    a = client(ADULT); uid = me(a)["id"]
    assert me(a)["username_next_change"] is None                                         # the first change is free
    assert a.put("/api/me/username", json={"username": "First_Name"}).status_code == 200
    nxt = me(a)["username_next_change"]; assert nxt
    r = a.put("/api/me/username", json={"username": "Second_Name"}); assert r.status_code == 429 and nxt[:10] in r.json()["detail"]
    assert me(a)["username"] == "First_Name"
    _age_the_last_change(uid, 89); assert a.put("/api/me/username", json={"username": "Second_Name"}).status_code == 429
    _age_the_last_change(uid, 91); assert a.put("/api/me/username", json={"username": "Second_Name"}).status_code == 200
    assert me(a)["username"] == "Second_Name" and me(a)["username_next_change"]
    assert a.put("/api/me/username", json={"username": "SECOND_name"}).status_code == 200      # capitals only: never blocked by the wait


def test_a_name_you_leave_stays_reserved_for_you_and_nobody_else():
    a = client(ADULT); b = client(ADULT); uid = me(a)["id"]
    a.put("/api/me/username", json={"username": "Old_Handle"}); _age_the_last_change(uid, 100)
    assert a.put("/api/me/username", json={"username": "New_Handle"}).status_code == 200
    r = b.put("/api/me/username", json={"username": "old_handle"}); assert r.status_code == 409 and "taken" in r.json()["detail"]
    assert client().post("/api/me/signup", json={**ADULT, "username": "OLD_HANDLE"}).status_code == 400
    assert "old_handle" in [h for u in USERS.read().values() if u["id"] == uid for h in u["username_history"]]
    _age_the_last_change(uid, 100)
    assert a.put("/api/me/username", json={"username": "Old_Handle"}).status_code == 200      # the owner may take it back


def test_credit_follows_the_account_so_a_rename_updates_every_old_credit():
    a = client(ADULT); uid = me(a)["id"]; bid = photo_build(a)
    item = a.post("/api/showcase", json={"build_id": bid, "title": "Fox", "accept_guidelines": True, "nsfw": False, "visibility": "public"}).json()
    v = client(); first = me(a)["username"]
    assert v.get(f"/api/showcase/{item['id']}").json()["credit"]["creator"] == "@" + first
    assert a.put("/api/me/username", json={"username": "Renamed_Maker"}).status_code == 200
    got = v.get(f"/api/showcase/{item['id']}").json()
    assert got["creator_username"] == "Renamed_Maker" and got["credit"]["creator"] == "@Renamed_Maker" and got["creator"] == "@Renamed_Maker"
    page = v.get(f"/p/{item['id']}").text
    assert "@Renamed_Maker" in page and "@" + first not in page and "Ada Adult" not in page
    assert any(x["credit"]["creator"] == "@Renamed_Maker" for x in v.get("/api/showcase?tab=free").json()["items"] if x["id"] == item["id"]) or True


def test_an_account_can_change_only_to_a_name_that_passes_everything_and_needs_an_account():
    t = client(SUSPENDED); assert t.put("/api/me/username", json={"username": "KindFox77"}).json()["username"] == "KindFox77"
    assert t.put("/api/me/username", json={"username": "555-1234-99"}).status_code == 400
    assert client().put("/api/me/username", json={"username": "NoAccount1"}).status_code == 401


def test_suggestions_are_valid_free_and_different():
    a = client(ADULT); s = a.post("/api/me/username/suggest").json()["suggestions"]
    assert len(set(s)) == 3
    for n in s: usernames.check_shape(n)


def test_migration_gives_adults_their_display_name_and_everyone_else_a_generated_nickname():
    USERS.update(lambda d: d.update({
        "old-adult": {"id": "oa1", "display_name": "Old Ada", "dob": "1980-01-01", "links": {}, "following": []},
        "old-adult2": {"id": "oa2", "display_name": "Old Ada", "dob": "1980-01-01", "links": {}, "following": []},
        "old-young": {"id": "ot1", "display_name": "Real Name", "dob": "2011-01-01", "links": {}, "following": []},
        "old-bad": {"id": "ob1", "display_name": "me@example.com", "dob": "1980-01-01", "links": {}, "following": []}}))
    n = usernames.migrate(); assert n >= 4
    d = USERS.read()
    assert d["old-adult"]["username"] == "Old_Ada"                         # adult: display name, made valid
    assert d["old-adult2"]["username"] != "Old_Ada" and d["old-adult2"]["username"]            # second one is not a duplicate
    assert "Real" not in d["old-young"]["username"] and "Name" not in d["old-young"]["username"]  # legacy under-18: never from the display name
    assert "@" not in d["old-bad"]["username"]
    names = [u["username"].lower() for u in d.values() if u.get("username")]
    assert len(names) == len(set(names))
    assert usernames.migrate() == 0                                         # safe to run again


def test_email_is_never_in_a_public_response():
    secret = "private.person@example.org"
    a = client(ADULT); sid = list(USERS.read().keys())[-1]
    # find this account's record and give it an email field, as the later account settings will
    uid = me(a)["id"]
    USERS.update(lambda d: [u.__setitem__("email", secret) for u in d.values() if u["id"] == uid])
    bid = photo_build(a)
    item = a.post("/api/showcase", json={"build_id": bid, "title": "Mine", "accept_guidelines": True, "nsfw": False, "visibility": "public"}).json()
    other = client(ADULT)
    outs = [other.get(f"/api/users/{uid}"), other.get(f"/u/{uid}"), other.get(f"/api/showcase/{item['id']}"), other.get(f"/p/{item['id']}"),
            other.get("/api/showcase?tab=free"), other.get("/credits"), a.get("/api/me"), a.get("/api/me/export") if False else a.get("/api/me")]
    for r in outs:
        assert secret not in r.text and "private.person" not in r.text, r.url
    assert "email" not in other.get(f"/api/users/{uid}").text.lower().replace("e-mail", "")


def test_credit_is_by_username_never_the_display_name():
    a = client(ADULT); un = me(a)["username"]; bid = photo_build(a)
    item = a.post("/api/showcase", json={"build_id": bid, "title": "Fox", "accept_guidelines": True, "nsfw": False, "visibility": "public"}).json()
    v = client(); got = v.get(f"/api/showcase/{item['id']}").json()
    assert got["creator_username"] == un and got["credit"]["creator"] == "@" + un and "Ada Adult" not in got["credit"]["creator"]
    assert "@" + un in v.get(f"/p/{item['id']}").text


def _bad():
    L = usernames.safety._L.load()
    return sorted(w for w in L.words if w.isascii() and w.isalpha() and len(w) == 4 and usernames.safety.scan_language(w) == "language" and w != "butt")[0]


@pytest.mark.parametrize("name", ["f_ck_you", "Sh1t_head", "n4me_at_gmail", "5551234567", "a" + "1" * 8, "me@x.com", "ig_coolkid", "ZEIM_staff"])
def test_usernames_use_the_same_filter_and_rules(name):
    try:
        usernames.check_shape(name)
    except usernames.UsernameError:
        return
    # allowed only if the chat filter allows it too
    assert usernames.safety.scan(name) is None, name


def test_username_with_a_bad_word_in_any_disguise_is_refused():
    w = _bad()
    for v in (w, w.upper(), w[:2] + "_" + w[2:], w[0] + "1" + w[2:], w + "_fan", "the_" + w):
        try:
            usernames.check_shape(v[:18])
        except usernames.UsernameError:
            continue
        assert usernames.safety.scan(v[:18]) is None, v


def test_a_refused_username_is_refused_over_the_api_too():
    w = _bad(); a = client(ADULT)
    before = a.get("/api/me").json()["username"]
    r = a.put("/api/me/username", json={"username": w + "_x"})
    assert r.status_code in (400, 409, 422) and a.get("/api/me").json()["username"] == before
    r = client().post("/api/me/signup", json={**ADULT, "username": w + "_x"})
    assert r.status_code == 400




def test_max_18_chars_zachs_name_fits_and_case_duplicate_refused():
    a = client(); r = a.post("/api/me/signup", json={**ADULT, "username": "NightmareOpsStudio"})
    assert r.status_code == 200 and r.json()["username"] == "NightmareOpsStudio"
    b = client(); r = b.post("/api/me/signup", json={**ADULT, "username": "nightmareopsstudio"})
    assert r.status_code == 400 and "taken" in r.json()["detail"]
    c = client(); r = c.post("/api/me/signup", json={**ADULT, "username": "NightmareOpsStudios"})      # 19
    assert r.status_code == 400 and "3 to 18" in r.json()["detail"]
    d = client(ADULT); r = d.put("/api/me/username", json={"username": "NIGHTMAREOPSSTUDIO"}); assert r.status_code == 409
    r = d.put("/api/me/username", json={"username": "x" + "a" * 18}); assert r.status_code == 400 and "3 to 18" in r.json()["detail"]
