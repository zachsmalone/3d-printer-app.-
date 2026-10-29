"""Showcase rest (task 4): print settings, Q&A, make settings/notes, prize-free remix challenge, camera capture attr."""
import io

import pytest
from PIL import Image

from app.community import challenges, print_settings as ps, questions
from app.community.store import CHALLENGE_ENTRIES, CHALLENGES, ENGAGEMENT, LISTINGS, MODERATION, PREFS, PRINTS, QUESTIONS
from tests.b1 import client, photo_build


@pytest.fixture(autouse=True)
def _fresh():
    snap = {s: s.read() for s in (LISTINGS, ENGAGEMENT, PREFS, PRINTS, MODERATION, QUESTIONS, CHALLENGES, CHALLENGE_ENTRIES)}
    yield
    for s, was in snap.items():
        s.write(was)


def U(n="Maker"):
    return client({"display_name": n, "dob": "1990-01-01"})


def publish(c, title="Pub", visibility="public", **extra):
    body = {"build_id": photo_build(c), "title": title, "description": "d",
            "tags": ["lamp"], "accept_guidelines": True, "nsfw": False,
            "visibility": visibility}
    body.update(extra)
    r = c.post("/api/showcase", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (200, 80, 100)).save(buf, format="PNG")
    return buf.getvalue()


# ---------- 1. print settings on models ----------
def test_print_settings_on_publish_and_filters():
    a = U("PsPub")
    i = publish(a, "With settings", print_settings={
        "printer": "fdm", "material": "pla", "layer_height_mm": 0.2, "infill_pct": 15,
        "supports": "no", "notes": "brim helped", "printer_name": "Prusa MK4"})
    assert i["print_settings"]["printer"] == "fdm"
    assert i["print_settings"]["material"] == "pla"
    assert i["print_settings"]["supports"] == "no"
    assert i["facets"]["printer"] == "fdm"
    assert i["facets"]["material"] == "pla"
    assert i["facets"]["supports"] == "no"
    # owner can clear / update
    r = a.put(f"/api/showcase/{i['id']}/print-settings", json={"print_settings": {"printer": "resin", "material": "resin", "supports": "yes"}})
    assert r.status_code == 200, r.text
    assert r.json()["print_settings"]["printer"] == "resin"
    assert r.json()["facets"]["printer"] == "resin"
    # bad value
    assert a.put(f"/api/showcase/{i['id']}/print-settings",
                 json={"print_settings": {"printer": "laser"}}).status_code == 400
    # stranger cannot edit
    b = U("PsOther")
    assert b.put(f"/api/showcase/{i['id']}/print-settings",
                 json={"print_settings": {"printer": "fdm"}}).status_code == 404


def test_print_settings_module_bounds():
    with pytest.raises(ps.Bad):
        ps.check({"layer_height_mm": 5})
    with pytest.raises(ps.Bad):
        ps.check({"infill_pct": -1})
    assert ps.check(None) == {}
    assert ps.check({}) == {}


# ---------- 2. creator-answered project questions ----------
def test_questions_filtered_no_dms_answered_public():
    a, b = U("Qcrea"), U("Qask")
    iid = publish(a, "Ask me")["id"]
    # asker posts
    r = b.post(f"/api/showcase/{iid}/questions", json={"text": "Will this print without supports?"})
    assert r.status_code == 200, r.text
    qid = r.json()["id"]
    assert r.json()["status"] == "open" and r.json()["mine"]
    # stranger does not see unanswered
    c = U("Qstranger")
    listed = c.get(f"/api/showcase/{iid}/questions").json()["questions"]
    assert listed == []
    # asker + creator see it
    assert any(q["id"] == qid for q in b.get(f"/api/showcase/{iid}/questions").json()["questions"])
    assert any(q["id"] == qid for q in a.get(f"/api/showcase/{iid}/questions").json()["questions"])
    # creator answers
    r = a.post(f"/api/showcase/{iid}/questions/{qid}/answer", json={"text": "Yes, on its side with a brim."})
    assert r.status_code == 200 and r.json()["status"] == "answered"
    # now public
    assert any(q["answer"].startswith("Yes") for q in c.get(f"/api/showcase/{iid}/questions").json()["questions"])
    # slur blocked
    bad = b.post(f"/api/showcase/{iid}/questions", json={"text": "you fucking idiot how do I print"})
    assert bad.status_code in (400, 422, 451) or (bad.status_code == 200 and False) or bad.status_code >= 400
    # no self-ask
    assert a.post(f"/api/showcase/{iid}/questions", json={"text": "hmm?"}).status_code == 400
    # asker deletes unanswered only — already answered, so delete by owner
    assert a.delete(f"/api/showcase/{iid}/questions/{qid}").status_code == 200


# ---------- 3. settings + notes on I printed this ----------
def test_print_photo_settings_and_notes():
    a, b = U("PrA"), U("PrB")
    iid = publish(a, "Printable")["id"]
    r = b.post(f"/api/showcase/{iid}/prints",
               files={"photo": ("p.png", _png(), "image/png")},
               data={"caption": "Solid", "photo_ack": "true", "nsfw": "no",
                     "printer": "fdm", "material": "pla", "layer_height_mm": "0.2",
                     "infill_pct": "20", "supports": "no", "notes": "0.2 mm, 20% gyroid",
                     "printer_name": "A1", "print_name": "First lamp"})
    assert r.status_code == 200, r.text
    body = r.json()
    s = body["settings"]
    assert s["printer"] == "fdm" and s["material"] == "pla" and s["infill_pct"] == 20
    assert "gyroid" in s["notes"]
    assert body["name"] == "First lamp" and s["printer_name"] == "A1" and "print_name" not in s
    long = b.post(f"/api/showcase/{iid}/prints",
                  files={"photo": ("p.png", _png(), "image/png")},
                  data={"photo_ack": "true", "nsfw": "no", "print_name": "x" * 81})
    assert long.status_code == 400
    # owner of photo sees it in list (pending)
    mine = b.get(f"/api/showcase/{iid}/prints").json()["prints"]
    assert mine and mine[0]["settings"]["material"] == "pla" and mine[0]["name"] == "First lamp"


# ---------- 4. prize-free remix challenge ----------
def test_remix_challenge_prize_free_enter():
    a, b = U("ChOrig"), U("ChRemix")
    src = publish(a, "Original lamp", license_id="cc-by-4.0")["id"]
    # remix
    rem = publish(b, "Remix lamp", remix_of=src, license_id="cc-by-4.0")
    assert rem.get("remix_of") == src or rem.get("credit")
    # list challenges — Remix seed always present, prize_free
    chs = b.get("/api/challenges").json()["challenges"]
    assert any(c["slug"] == "remix" and c["prize_free"] is True for c in chs)
    cid = next(c["id"] for c in chs if c["slug"] == "remix")
    detail = b.get(f"/api/challenges/{cid}").json()
    assert detail["prize_free"] is True
    assert "no cash" in detail["blurb"].lower() or any("prize" in r.lower() for r in detail["rules"])
    assert any("never takes a cut" in r for r in detail["rules"])
    # enter
    r = b.post(f"/api/challenges/{cid}/enter", json={"item_id": rem["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["prize_free"] is True
    assert "Prize-free" in r.json()["message"] or "prize" in r.json()["message"].lower()
    # non-remix refused
    plain = publish(b, "Not a remix")["id"]
    assert b.post(f"/api/challenges/{cid}/enter", json={"item_id": plain}).status_code == 400
    # one entry per person
    rem2 = publish(b, "Second remix", remix_of=src, license_id="cc-by-4.0")["id"]
    assert b.post(f"/api/challenges/{cid}/enter", json={"item_id": rem2}).status_code == 400


def test_challenge_eligible_lists_own_published_showcase_items():
    """The enter dialog picks from published Showcase projects. Studio files, private posts, and other people stay out."""
    a, b = U("ElOrig"), U("ElRemix")
    src = publish(a, "Source cup", license_id="cc-by-4.0")
    rem = publish(b, "My cup remix", remix_of=src["id"], license_id="cc-by-4.0")
    plain = publish(b, "Plain cup")
    priv = publish(b, "Private remix", remix_of=src["id"], license_id="cc-by-4.0", visibility="private")
    other = publish(a, "Other remix", remix_of=src["id"], license_id="cc-by-4.0")
    cid = challenges.REMIX_ID
    anon = client().get(f"/api/challenges/{cid}/eligible")
    assert anon.status_code == 200 and anon.json()["signed_in"] is False and anon.json()["items"] == []
    assert client().get("/api/challenges/no-such-challenge/eligible").status_code == 404
    body = b.get(f"/api/challenges/{cid}/eligible").json()
    assert body["signed_in"] is True and body["already_entered"] is False and body["can_enter"] is True
    ids = [i["id"] for i in body["items"]]
    assert rem["id"] in ids and plain["id"] in ids and other["id"] not in ids and priv["id"] not in ids
    hit = next(i for i in body["items"] if i["id"] == rem["id"])
    assert hit["remix_of"] == src["id"] and hit["remix_title"] == "Source cup" and hit["share_url"] == f"/p/{rem['id']}"
    assert b.post(f"/api/challenges/{cid}/enter", json={"build_id": "aaaaaaaaaaaa"}).status_code == 400
    assert b.post(f"/api/challenges/{cid}/enter", json={"item_id": rem["id"]}).status_code == 200
    again = b.get(f"/api/challenges/{cid}/eligible").json()
    assert again["already_entered"] is True and again["can_enter"] is False
    assert again["entry"]["item_id"] == rem["id"] and again["entry"]["title"] == "My cup remix"


def test_old_tip_rule_is_replaced_once():
    CHALLENGES.write([{"id": challenges.REMIX_ID, "slug": "remix", "prize_free": True, "created": 1,
                       "rules": ["Prize-free: ZEIM offers no cash or prizes for this challenge.", challenges._OLD_TIP_RULE]}])
    challenges._ensure_seed()
    rules = CHALLENGES.read()[0]["rules"]
    assert challenges._OLD_TIP_RULE not in rules
    assert any("never takes a cut" in r for r in rules)
    challenges._ensure_seed()
    assert CHALLENGES.read()[0]["rules"] == rules


# ---------- 5. phone camera capture attribute in shipped UI ----------
def test_camera_capture_in_community_js():
    js = open("static/community.js").read()
    assert 'capture="environment"' in js
    assert "prCam" in js
    assert 'id="prName"' in js and 'accept="image/*" multiple' in js
    assert "Print notes" in js and "showoff-pick" in js
    assert "Ask the creator" in js
    assert "Prize-free" in js or "prize-free" in js.lower()
    html = open("static/index.html").read()
    assert 'id="chStrip"' in html and 'id="pubPs"' in html
