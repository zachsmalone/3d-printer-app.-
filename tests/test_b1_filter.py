"""Filter fixes from Kenji's red-team (reports/filter-redteam.md) and the cases Zach/Kenji listed. Abusive words are taken from the
app's own word lists at run time, so this file contains none."""
import shutil
import pytest
from app.community import safety
from tests.b1 import client, ADULT
from tests.test_b1_edit_text import new_edit, text_op

MUST_PASS = [
    "Niger", "Nigeria", "Nigerian", "white power supply", "power supply", "Printed on 2026-10-04", "0.2 0.4 0.6 0.8 1.0 mm",
    "serial 1234567890", "benchy.me", "index.io", "main.dev", "Fusion360.app", "Meet @ 5pm. at home.",
    "class", "assess", "assemble", "cockpit", "Hancock", "nozzle", "infill", "raft", "brim",
    "rabbit chair", "mini game", "a bit cheap", "habit change", "Material: PLA, information and rights", "license and conditions",
    "Printed at school. Info below", "Discord is fun", "WhatsApp is popular", "Temps 200 210 220 230 240", "Serial no 12 34 56 78 90",
    "Price 19.99 29.99 39.99 49.99", "Print time 12:30 on 2026-10-04 12:45", "The model.stl file", "Version 1.2.3", "1 2 3 4 5 6 7 8 9 10", "Layer 0.2 mm, 15% infill",
]
MUST_BLOCK_CONTACT = [
    "kid@example.com", "name at gmail dot com", "name AT gmail DOT com", "kid (at) example (dot) com", "name at gmail",
    "kid [at] example [dot] com", "555-123-4567", "(555) 123-4567", "+44 7911 123456", "call me 555 1234",
    "five five five one two three four", "cinco cinco cinco uno dos tres cuatro", "five 5 5 one two three 4",
    "@kid_name", "kid#1234", "https://x.example/a", "http://x.example", "www.example.com", "x.com", "example dot com",
    "benchy.me/abc", "insta: kidname", "snapchat: cool_kid9", "my discord is kid99", "12 Oak Street", "PO Box 123",
    "johnsmith <at> gmail <dot> com", "johnsmith-at-gmail-dot-com", "johnsmith arroba gmail punto com", "555,123,4567", "555/123/4567",
    "07700 900123", "192.168.1.20", "example[.]com", "hxxps://example[.]com", "u/coolkid99", "ig: coolkid99", "call 5551234567",
    "kid\u200b@example.com", "k\u200bid@exa\u200bmple.com", "ｋｉｄ＠ｅｘａｍｐｌｅ．ｃｏｍ",          # zero-width / fullwidth
]


@pytest.mark.parametrize("t", MUST_PASS)
def test_must_pass(t):
    assert safety.scan(t) is None, t


@pytest.mark.parametrize("t", MUST_BLOCK_CONTACT)
def test_must_block_contact(t):
    assert safety.scan(t) == "contact_info", t


def _sample_words(n=40):
    L = safety._L.load()
    ws = sorted(w for w in L.words if w.isascii() and w.isalpha() and 4 <= len(w) <= 8 and safety.scan_language(w) == "language")
    return ws[:: max(1, len(ws) // n)][:n]


TRANSFORMS = {
    "zero-width space": lambda w: w[:2] + "\u200b" + w[2:],
    "zero-width joiner": lambda w: w[:2] + "\u200d" + w[2:],
    "soft hyphen": lambda w: w[:2] + "\u00ad" + w[2:],
    "tag char": lambda w: w[:2] + "\U000e0041" + w[2:],
    "variation selector": lambda w: w[:2] + "\ufe0f" + w[2:],
    "Cyrillic o/a/e/c/p": lambda w: w.translate(str.maketrans("aeocp", "аеоср")),
    "Greek o/a": lambda w: w.translate(str.maketrans("oa", "οα")),
    "small caps": lambda w: w.translate(str.maketrans("abcdefghijklmnopqrstuvwxyz", "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢ")),
    "squared letters": lambda w: "".join(chr(0x1F130 + ord(c) - 97) for c in w),
    "dot inserted": lambda w: w[:2] + "." + w[2:],
    "hyphen inserted": lambda w: w[:2] + "-" + w[2:],
    "underscore inserted": lambda w: w[:2] + "_" + w[2:],
    "star replaces a letter": lambda w: w[:1] + "*" + w[2:],
    "every letter doubled": lambda w: "".join(c * 2 for c in w),
    "stretched": lambda w: w[0] * 3 + w + w[-1] * 3,
    "fullwidth": lambda w: "".join(chr(ord(c) + 0xFEE0) for c in w),
}


@pytest.mark.parametrize("name", sorted(TRANSFORMS))
def test_evasions_are_caught(name):
    words, fn = _sample_words(), TRANSFORMS[name]
    missed = [w for w in words if not safety.scan_language(fn(w))]
    # a few list entries are too short/ambiguous to catch once a character is replaced (e.g. star replacing the only vowel); require >= 90 %
    assert len(missed) <= max(2, len(words) // 10), (name, len(missed), len(words))


def test_licence_text_is_not_a_word_list():
    L = safety._L.load()
    assert {"material", "information", "rights", "license", "conditions", "warranties"}.isdisjoint(L.words)
    assert safety.scan("Material: PLA. Information, rights and license.") is None


def test_only_intended_files_are_loaded(tmp_path, monkeypatch):
    wl = tmp_path / "wl"; shutil.copytree(safety.WL, wl)
    (wl / "notes.txt").write_text("flibbertigibbet\n")                              # a stray file must NOT become a word list
    monkeypatch.setattr(safety, "WL", wl); safety._L.sig = None
    assert safety.scan("flibbertigibbet") is None
    monkeypatch.undo(); safety._L.sig = None


def test_missing_wordlists_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(safety, "WL", tmp_path / "does-not-exist"); safety._L.sig = None
    try:
        with pytest.raises(safety.ChatBlocked) as e:
            safety.check("Hello world", "Title")
        assert e.value.status == 503 and e.value.payload["code"] == "filter_unavailable"
        assert safety.check("", "Title") == ""                                            # nothing to check
    finally:
        monkeypatch.undo(); safety._L.sig = None
    assert safety.check("Hello world", "Title") == "Hello world"                          # and it recovers when the lists are back


def test_one_error_shape_for_every_refused_text():
    a, kid = client(ADULT), client()
    lang = safety._L.load()
    bad = next(w for w in sorted(lang.words) if w.isalpha() and w.isascii() and len(w) >= 5 and safety.scan_language(w))
    shapes = []
    shapes.append(a.post("/api/me/signup", json={"display_name": bad, "dob": "1990-01-01"}))
    shapes.append(a.post("/api/classrooms", json={"name": bad, "password": "plum-otter-42"}))
    shapes.append(a.put("/api/me/links", json={"instagram": bad}))
    bid = new_edit(a)
    shapes.append(text_op(a, bid, bad))
    for r in shapes:
        j = r.json()
        assert r.status_code == 422 and set(j) >= {"code", "message", "context", "detail"} and j["detail"] == j["message"], (r.request.url, r.status_code, j)


def test_profile_link_handles_use_the_same_filter():
    a = client(ADULT)
    r = a.put("/api/me/links", json={"instagram": "kid#1234"})
    assert r.status_code in (400, 422)                                                    # '#' is not a valid handle character anyway
    bad = next(w for w in sorted(safety._L.load().words) if w.isalpha() and w.isascii() and len(w) >= 5 and safety.scan_language(w))
    r = a.put("/api/me/links", json={"tiktok": bad})
    assert r.status_code == 422 and r.json()["code"] == "language_blocked"
    r = a.put("/api/me/links", json={"tiktok": "maker.fan"})
    assert r.status_code == 200


def test_edit_text_zero_width_and_spelled_out_pii_are_refused():
    c = client(); bid = new_edit(c)
    L = safety._L.load()
    bad = next(w for w in sorted(L.words) if w.isalpha() and w.isascii() and len(w) >= 5 and safety.scan_language(w))
    for t in (bad[:2] + "\u200b" + bad[2:], "name at gmail dot com", "five five five one two three four", "@kid_name", "12 Oak Street"):
        assert text_op(c, bid, t).status_code == 422, repr(t)
    from app.services.editproj import store  # noqa  (nothing stored)
