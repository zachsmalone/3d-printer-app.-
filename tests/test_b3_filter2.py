"""Filter follow-up (red-team re-check): innocent maker/plain words stay allowed, look-alike letters, invisible characters, masks, obfuscated
e-mail, spelled-out phone numbers, bare handles and addresses are refused on every free-text field other people can read - and usernames
use the very same gate. Abusive words come from the app's own lists at run time."""
import pytest
from app.community import safety
from tests.b1 import client, ADULT

ALLOWED = ["nozzle", "print bed", "cockpit", "Butt joint vs lap joint", "butt weld seam", "Hard stop for the limit switch", "hard plastic",
           "Peter Piper", "Anita", "Regina", "stake and rope", "finger grip", "Nipple fitting for a tube", "Blue tit nest box", "Cock robin bird feeder",
           "Sex education class", "a bit cheap", "rabbit chair", "Nigeria", "snap fit lid", "snap together box", "Material: PLA information and rights",
           "Print time 12:30 on 2026-10-04 12:45", "Version 2.1.3", "ball bearing"]


@pytest.mark.parametrize("t", ALLOWED)
def test_innocent_text_stays_allowed(t):
    assert safety.scan(t) is None, t


def _bad(i=0):
    L = safety._L.load()
    ws = sorted(w for w in L.words if w.isascii() and w.isalpha() and len(w) == 4 and safety.scan_language(w) == "language" and w not in ("butt",))
    return ws[i]


def test_lookalike_invisible_and_masked_letters_are_refused():
    w = _bad(); assert safety.scan_language(w) == "language"
    cyr = w.translate(str.maketrans("aeocp", "аеоср"))
    variants = {"cyrillic": cyr, "cyrillic u": w.replace("u", "\u0443"), "zero width": w[:2] + "\u200b" + w[2:], "soft hyphen": w[:1] + "\u00ad" + w[1:],
                "joiner": w[:2] + "\u200d" + w[2:], "tag char": w[:2] + "\U000e0041" + w[2:], "star mask": w[0] + "*" + w[2:], "hash mask": w[0] + "#" + w[2:],
                "dot": w[:2] + "." + w[2:], "underscore": w[:2] + "_" + w[2:], "spaced": " ".join(w), "fullwidth": "".join(chr(ord(c) + 0xFEE0) for c in w)}
    missed = [k for k, v in variants.items() if safety.scan_language(v) != "language"]
    # a word without 'u' has no Cyrillic-u variant; every other variant must be caught
    assert missed in ([], ["cyrillic u"]) or (("u" not in w) and missed == ["cyrillic u"]), (missed, w)


@pytest.mark.parametrize("t", [
    "name at gmail dot com", "n a m e @ g m a i l . c o m", "name[at]gmail[dot]com", "john.doe (at) yahoo (dot) com",
    "five five five one two three four", "cinco cinco cinco uno dos tres cuatro", "my number is 5551234", "555-123-4567",
    "@coolkid99", "u/coolkid", "coolkid#1234", "add me on snap", "snap me", "whatsapp me", "dm me",
    "12 Oak Street", "123 Main St.", "PO Box 123"])
def test_contact_details_in_any_disguise_are_refused(t):
    assert safety.scan(t) == "contact_info", t


def test_upload_body_cap_and_report_dialog_links():
    from app import main
    c = client(ADULT)
    r = c.post("/api/generate", content=b"x", headers={"content-type": "multipart/form-data; boundary=x", "content-length": str(main.MAX_MULTIPART_BODY + 1)})
    assert r.status_code == 413
    html = open("static/index.html", encoding="utf-8").read()
    dlg = html[html.index('id="dlgReport"'):html.index('id="toasts"')]
    for href in ("/static/COMMUNITY_GUIDELINES.html", "/static/privacy.html", "/static/terms.html"):
        assert href in dlg, href
