"""QA fixes for the Showcase small upgrades (B1-B6)."""
import os
import re

import pytest

from app.community import tips
from app.community.store import ENGAGEMENT, LISTINGS, MODERATION, PREFS, PRINTS
from tests.b1 import client, photo_build

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = open(os.path.join(ROOT, "static", "community.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "static", "style.css"), encoding="utf-8").read()
HTML = open(os.path.join(ROOT, "static", "index.html"), encoding="utf-8").read()


@pytest.fixture(autouse=True)
def _fresh():
    snap = {s: s.read() for s in (LISTINGS, ENGAGEMENT, PREFS, PRINTS, MODERATION)}
    yield
    for s, was in snap.items():
        s.write(was)


# B1: AI filter choice persists (URL ?ai= first, then localStorage)
def test_b1_ai_filter_persists():
    assert 'localStorage.setItem("zeim.showcase.ai"' in JS and 'localStorage.getItem("zeim.showcase.ai")' in JS
    assert 'searchParams.set("ai"' in JS and 'URLSearchParams(location.search).get("ai")' in JS
    assert "history.replaceState" in JS


# B2: empty result with a filter on says filters are hiding results + Reset filters
def test_b2_filtered_empty_state_offers_reset():
    assert "Your filters are hiding results" in JS and '"Reset filters"' in JS
    assert 'shAiVal() !== "show"' in JS and '[data-empty="reset-filters"]' in JS


# B3: publish form locks the AI box for 2D->3D builds, matching the server
def test_b3_publish_ai_box_locked_for_ai3d():
    assert 'src?.mode === "ai3d"' in JS and "aiBox.disabled = aiForced" in JS
    assert 'id="pub_ai_note" hidden' in HTML and "always labelled AI-made" in HTML


def test_b3_server_forces_ai_for_ai3d_build():
    from app.community import catalog
    src = open(catalog.__file__, encoding="utf-8").read()
    assert 'bool(bmeta.get("ai")) or bmeta.get("mode") == "ai3d"' in src


# B4: long titles wrap/ellipsize on both card styles
def test_b4_card_titles_wrap_and_ellipsize():
    assert re.search(r"\.pcard \.meta b,\.pcard \.meta h2 a\{overflow-wrap:anywhere", CSS)
    assert re.search(r"\.pcard \.meta h2 a\{[^}]*text-overflow:ellipsis", CSS)
    assert re.search(r"\.pcard \.meta b\{[^}]*text-overflow:ellipsis", CSS)


# B5: scheme/host normalised to lowercase; client check case-insensitive
def test_b5_tip_normalised_lowercase():
    assert tips.check("HTTPS://KO-FI.COM/x") == "https://ko-fi.com/x"
    assert tips.check("https://Ko-Fi.com/MyName?A=B") == "https://ko-fi.com/MyName?A=B"
    assert "/^https:\\/\\//i.test(i.tip_url" in JS


def test_b5_tip_normalised_via_api():
    c = client({"display_name": "Tipper", "dob": "1990-01-01"})
    r = c.post("/api/showcase", json={"build_id": photo_build(c), "title": "T", "description": "d", "tags": ["lamp"],
                                      "accept_guidelines": True, "nsfw": False, "visibility": "public", "tip_url": "HTTPS://KO-FI.COM/x"})
    assert r.status_code == 200, r.text
    assert r.json()["tip_url"] == "https://ko-fi.com/x"
    r = c.put(f"/api/showcase/{r.json()['id']}/tip", json={"tip_url": "HTTPS://Buymeacoffee.COM/Y"})
    assert r.status_code == 200 and r.json()["tip_url"] == "https://buymeacoffee.com/Y"


# B6: private suffixes, embedded IPv4 rebinding hosts, Cf/Cc characters
@pytest.mark.parametrize("bad", [
    "https://foo.localhost/x", "https://svc.internal/x", "https://printer.local/x", "https://nas.lan/x",
    "https://router.home/x", "https://1.0.0.127.in-addr.arpa/x", "https://127.0.0.1.nip.io/x",
    "https://10-0-0-1.sslip.io/x", "https://a.192.168.1.1.example.com/", "https://ko-fi.com/a\u200bb",
    "https://ko-fi.com/\u202emoc", "https://ko-fi.com/a\u2066b", "https://ko-fi.com/a\x7f", "https://ko-fi.com/x%E2%80%8B", "https://ko\u200d-fi.com/x", "https://ko-fi.com/x\u0085",
])
def test_b6_tip_rejects_private_and_hidden(bad):
    with pytest.raises(ValueError):
        tips.check(bad)


@pytest.mark.parametrize("ok", ["https://ko-fi.com/x", "https://www.patreon.com/someone", "https://buymeacoffee.com/a1b2"])
def test_b6_tip_still_accepts_public(ok):
    assert tips.check(ok) == ok


# NOTE: likes / prints_count / sort=printed are intentionally kept
def test_printed_sort_kept():
    assert "prints_count" in open(os.path.join(ROOT, "app", "community", "catalog.py"), encoding="utf-8").read()


# ================= Trust & Safety batch (lindsi-tip-ailabel-01d4f9d) =================
from app.services import editproj
from app.services.history import store as bstore


def U(n):
    return client({"display_name": n, "dob": "1990-01-01"})


def pub(c, bid, title="P", **extra):
    r = c.post("/api/showcase", json={"build_id": bid, "title": title, "description": "d", "tags": ["lamp"],
                                      "accept_guidelines": True, "nsfw": False, "visibility": "public", **extra})
    assert r.status_code == 200, r.text
    return r.json()


def ai_build(c):
    bid = photo_build(c)
    m = bstore.get(bid); m["ai"] = True; bstore.save(m)      # same shape as a 2D->3D build's meta
    return bid


def edit_from(c, bid, **form):
    r = c.post("/api/edit/new", data={"from_build": bid, **form})
    assert r.status_code == 200, r.text
    return r.json()["id"]


# F1: AI provenance survives Edit, Save as new version and re-upload of its own 3MF
def test_f1_ai_survives_edit_version_and_reupload(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "DUPLICATE_CHECK", False)
    c = U("Laund")
    src = ai_build(c)
    e1 = edit_from(c, src)
    assert bstore.get(e1).get("ai") is True and bstore.get(e1)["parent_build"] == src
    e2 = edit_from(c, e1, keep_history="true")                       # Save as a new version
    assert bstore.get(e2).get("ai") is True and editproj.ai_lineage(bstore.get(e2))
    data = c.get(f"/api/download/{e2}/3mf").content
    assert editproj.ai_in_3mf(data)        # F8 export
    r = c.post("/api/edit/new", files={"file": ("x.3mf", data, "model/3mf")}, data={"units": "mm"})
    assert r.status_code == 200, r.text
    e3 = r.json()["id"]
    assert bstore.get(e3).get("ai") is True                          # F8 import
    for b in (e1, e2, e3):
        it = pub(c, b, "AI " + b[:4])
        assert it["ai_made"] is True and it["ai_locked"] is True
        r = c.put(f"/api/showcase/{it['id']}/ai", json={"ai_made": False})
        assert r.status_code == 400


def test_f1_plain_build_not_marked():
    c = U("Plain")
    e = edit_from(c, photo_build(c))
    assert not bstore.get(e).get("ai") and not editproj.ai_lineage(bstore.get(e))


# F8: showcase download carries zeim:AIMade for AI-made items
def test_f8_owner_meta_has_ai_flag():
    from app.community import protect
    assert protect.owner_meta({"id": "x", "ai_made": True})["zeim:AIMade"] == "true"
    assert "zeim:AIMade" not in protect.owner_meta({"id": "x"})


# F3: destination shown, shorteners/redirectors and punycode refused
@pytest.mark.parametrize("bad", ["https://bit.ly/3abcde", "https://t.co/x", "https://tinyurl.com/x", "https://goo.gl/x",
                                 "https://www.google.com/url?q=https://evil.example", "https://xn--pypal-4ve.com/",
                                 "https://pay.xn--ko-fi-6ve.com/x"])
def test_f3_redirectors_and_punycode_refused(bad):
    with pytest.raises(ValueError):
        tips.check(bad)


def test_f3_f10_tip_text_shows_domain_neutrally():
    assert "Tip link for ${esc(who)} (${esc(host)})" in JS
    assert "Want to support" not in JS
    assert tips.domain("https://Ko-Fi.com/x") == "ko-fi.com"


# F5: moderator removes only the tip link; queue shows it; owner blocked while hidden
def test_f5_moderation_tip(monkeypatch):
    from app import config
    from app.api import community as api
    from app.community import moderation
    monkeypatch.setattr(config, "ADMIN_TOKEN", "t0k")
    c = U("Modtip")
    it = pub(c, photo_build(c), "Tipped", tip_url="https://ko-fi.com/modtip")
    assert api._preview(it["id"])["tip_url"] == "https://ko-fi.com/modtip"
    MODERATION.update(lambda m: m["hidden"].append(it["id"]))
    r = c.put(f"/api/showcase/{it['id']}/tip", json={"tip_url": "https://ko-fi.com/other"})
    assert r.status_code == 403
    assert c.post(f"/api/moderation/item/{it['id']}/tip", json={}, headers={"x-admin-token": "nope"}).status_code == 403
    r = c.post(f"/api/moderation/item/{it['id']}/tip", json={"reason": "scam"}, headers={"x-admin-token": "t0k"})
    assert r.status_code == 200
    assert next(i for i in LISTINGS.read() if i["id"] == it["id"])["tip_url"] == ""
    assert any(e["action"] == "tip_removed" for e in moderation.audit_trail())
    assert c.post("/api/moderation/item/nope404/tip", json={}, headers={"x-admin-token": "t0k"}).status_code == 404


# F6: 10 tip/AI changes per hour per user
def test_f6_rate_limit():
    c = U("Spammy")
    it = pub(c, photo_build(c), "Rl")
    codes = [c.put(f"/api/showcase/{it['id']}/tip", json={"tip_url": f"https://ko-fi.com/n{k}"}).status_code for k in range(6)]
    codes += [c.put(f"/api/showcase/{it['id']}/ai", json={"ai_made": bool(k % 2)}).status_code for k in range(5)]
    assert codes[:10] == [200] * 10 and codes[10] == 429


# F9: a remix of an AI-made model inherits a locked AI-made label
def test_f9_remix_inherits_ai(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "DUPLICATE_CHECK", False)
    a = U("AiMaker")
    src = pub(a, photo_build(a), "AiSrc", ai_made=True, license_id="cc-by-4.0")
    b = U("Remixer")
    rem = pub(b, photo_build(b), "Remix", remix_of=src["id"], license_id="cc-by-4.0")
    assert rem["ai_made"] is True and rem["ai_locked"] is True
    assert b.put(f"/api/showcase/{rem['id']}/ai", json={"ai_made": False}).status_code == 400
    plain = pub(b, photo_build(b), "NotRemix")
    assert plain["ai_made"] is False and plain["ai_locked"] is False


# F11: emails / phone numbers in the tip URL refused by the personal-info filter
@pytest.mark.parametrize("bad", ["https://ko-fi.com/jane.doe@example.com", "https://ko-fi.com/a?phone=555-0100",
                                 "https://ko-fi.com/jane.doe%40example.com"])
def test_f11_personal_info_refused(bad):
    with pytest.raises(ValueError):
        tips.check(bad)
