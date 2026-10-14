"""Mild NSFW (artistic nudity / figure sculpts) is allowed when tagged: listed as blurred cards, optional 'hide entirely' setting,
moderators can flip the tag; explicit terms stay blocked everywhere."""
import os
import pytest
from app.community import safety
from tests.b1 import client, photo_build, jpeg_with_gps, ADULT, ADMIN

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def U(n):
    return client({"display_name": n, "dob": "1990-01-01"})


def pub(c, title, nsfw, **kw):
    return c.post("/api/showcase", json={"build_id": photo_build(c), "title": title, "description": kw.pop("desc", ""), "tags": [],
                                         "accept_guidelines": True, "visibility": "public", **({"nsfw": nsfw} if nsfw is not None else {})})


def ids(c, **p):
    return {i["id"]: i for i in c.get("/api/showcase", params={"tab": "free", **p}).json()["items"]}


def test_question_is_required_and_stored():
    a = U("Na")
    r = pub(a, "No answer", None)
    assert r.status_code == 422 and "NSFW" in r.text
    assert pub(a, "Clean", False).json()["nsfw"] is False
    assert pub(a, "Figure study", True).json()["nsfw"] is True


def test_filter_allows_mild_words_only_when_tagged_and_explicit_always_blocked():
    a = U("Nb")
    assert pub(a, "Nude figure sculpt", False).status_code == 422
    r = pub(a, "Nude figure sculpt", True, desc="artistic nudity, classical pose"); assert r.status_code == 200, r.text
    assert pub(a, "porn statue", True).status_code == 422
    assert pub(a, "nudes for sale", True).status_code == 422
    assert safety.scan("nude torso", nsfw=True) is None and safety.scan("nude torso") == "language"
    assert safety.scan("porn", nsfw=True) == "language"
    with pytest.raises(ValueError):
        safety.parse_nsfw("maybe")


def test_listed_blurred_by_default_and_hide_setting():
    a = U("Nc"); it = pub(a, "Venus sculpt", True).json()
    v = U("Nv")
    got = ids(v, q="venus")
    assert it["id"] in got and got[it["id"]]["nsfw"] is True              # shown (client blurs it), not hidden
    assert it["id"] in ids(client(), q="venus")                           # signed-out visitors too
    assert v.get("/api/me").json()["hide_mature"] is False
    assert v.put("/api/me/mature", json={"hide_mature": True}).json() == {"hide_mature": True}
    assert it["id"] not in ids(v, q="venus")
    assert it["id"] in ids(a, q="venus")                                  # the owner always sees their own
    assert client().put("/api/me/mature", json={"hide_mature": True}).status_code == 401


def test_print_photo_question_and_flag():
    a = U("Nd"); it = pub(a, "Bust", False).json(); v = U("Nw")
    url = f"/api/showcase/{it['id']}/prints"
    assert v.post(url, files={"photo": ("p.jpg", jpeg_with_gps(), "image/jpeg")}).status_code == 400
    p = v.post(url, files={"photo": ("p.jpg", jpeg_with_gps(), "image/jpeg")}, data={"nsfw": "yes", "caption": "nude bust"})
    assert p.status_code == 200, p.text
    assert p.json()["nsfw"] is True
    q = client().get("/api/moderation/queue", headers=ADMIN).json()["pending_prints"]
    assert any(x["id"] == p.json()["id"] and x["nsfw"] is True for x in q)
    assert client().post(f"/api/moderation/item/print:{p.json()['id']}/nsfw", json={"nsfw": False}, headers=ADMIN).json()["nsfw"] is False


def test_share_page_hides_mature_picture_until_confirmed():
    a = U("Ns"); it = pub(a, "Figure", True).json(); v = U("Ny")
    html = v.get(f"/p/{it['id']}").text
    assert "<details class=mature-share>" in html and "Are you sure? This may contain nudity." in html and "sharethumb" in html
    assert "mature-share" not in a.get(f"/p/{it['id']}").text            # the owner sees their own picture
    clean = pub(a, "Vase", False).json()
    assert "mature-share" not in v.get(f"/p/{clean['id']}").text


def test_print_gallery_and_moderation_ui_wiring():
    js = open(os.path.join(ROOT, "static/community.js")).read(); mj = open(os.path.join(ROOT, "static/moderation.js")).read()
    assert "data-prshow" in js and "prmature" in js and "confirmMature()" in js
    assert "mark_nsfw" in mj and "unmark_nsfw" in mj and '"remove"' in mj and "/nsfw`" in mj


def test_moderator_flips_tag_and_report_reason():
    a = U("Ne"); it = pub(a, "Statue", False).json(); v = U("Nx")
    r = v.post(f"/api/showcase/{it['id']}/report", json={"reason": "should_be_nsfw", "details": ""})
    assert r.status_code == 200 and not r.json()["auto_hidden"]
    assert client().post(f"/api/moderation/{r.json()['id']}/resolve", json={"action": "mark_nsfw"}, headers=ADMIN).status_code == 200
    assert v.get(f"/api/showcase/{it['id']}").json()["nsfw"] is True
    assert client().post(f"/api/moderation/item/{it['id']}/nsfw", json={"nsfw": False}, headers=ADMIN).json()["nsfw"] is False
    assert client().post(f"/api/moderation/item/{it['id']}/nsfw", json={"nsfw": True}).status_code == 403
    r2 = v.post(f"/api/showcase/{it['id']}/report", json={"reason": "not_family_friendly", "details": ""}).json()
    assert client().post(f"/api/moderation/{r2['id']}/resolve", json={"action": "remove"}, headers=ADMIN).status_code == 200
    assert v.get(f"/api/showcase/{it['id']}").status_code == 404


def test_ui_and_docs():
    js = open(os.path.join(ROOT, "static/community.js")).read(); html = open(os.path.join(ROOT, "static/index.html")).read()
    assert "Are you sure? This may contain nudity." in html and "Mature content" in js and "sessionStorage" in js
    assert 'name="pub_nsfw"' in html and "Hide mature content entirely" in (html + js) and "should_be_nsfw" in html
    readme = open(os.path.join(ROOT, "README.md")).read()
    assert "No NSFW" not in readme and "Mild NSFW" in readme
    for f in ("static/COMMUNITY_GUIDELINES.md", "static/COMMUNITY_GUIDELINES.html", "static/terms.html"):
        t = open(os.path.join(ROOT, f)).read(); assert "blurred" in t and "xplicit" in t, f
