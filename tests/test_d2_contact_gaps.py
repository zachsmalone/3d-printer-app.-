"""Chat-filter red-team follow-up (2026-10-13): contact details hidden with zero-width characters, spelled-out phone numbers
(including 'triple five' and words glued together), e-mails/links written as words, bare @handles and disguised platform names
are refused - while ordinary maker talk with numbers, counting and product names still passes."""
import pytest
from app.community import safety

Z, ZJ, WJ, BOM = "\u200b", "\u200d", "\u2060", "\ufeff"

BLOCK = [
    # zero-width characters hidden inside contact info
    f"5{Z}5{Z}5{Z}1{Z}2{Z}3{Z}4{Z}5{Z}6{Z}7", f"555{Z}1234", f"555{Z}123{Z}4567", f"5 5 5 {Z}1 2 3 4 5 6 7",
    f"name@gm{ZJ}ail.c{Z}om", f"@{Z}makerguy", f"follow me @{BOM}makerguy", f"my{Z}snap is makerguy", f"example{WJ}.{Z}com",
    # spelled-out contact details
    "five five five one two three four", "triple five one two three four", "double five five one two three four five",
    "fivefivefive onetwothree fourfivesixseven", "nine one seven, five five five, oh one two three", "5 5 5 1 2 3 4 5 6 7",
    "name at gmail dot com", "email me at johnsmith gmail com", "jsmith99 gmail com", "maker dot io", "example dot com",
    # bare @handles / off-platform contact
    "@makerguy", "IG @makerguy", "follow @maker_guy99", "insta coolkid99", "xbox gamertag coolkid99", "pm me",
    "facetime me at coolkid99", "d1scord: coolkid99", "s.n.a.p: coolkid99", "s n a p coolkid99",
]

ALLOW = [
    "zero one two three four five six seven eight nine number stencil", "count: one, two, three, four, five, six, seven",
    "1 2 3 4 5 6 7 8 9 10 steps", "0 0 0 0 0 0 0 0 0 0", "Print one for each of my nine nieces and five nephews",
    "I use gmail com as my login", "xbox 360 controller stand", "minecraft 1.20 mod", "steam deck v2 stand", "Snap fit lid v2",
    "Discord bot project for class", "Polka dot vase", "Print @ 200C", "Temps 200 210 220 230 240", "Serial no 12 34 56 78 90",
    f"Ma{Z}terial PLA", f"ver{Z}sion 2.1.3", f"nozzle 0.4{Z} mm", "Print time 12:30 on 2026-10-04 12:45", "G1 X10.5 Y20.25 Z0.2 F1500",
]


@pytest.mark.parametrize("t", BLOCK)
def test_hidden_and_spelled_contact_details_are_refused(t):
    assert safety.scan(t) == "contact_info", repr(t)


@pytest.mark.parametrize("t", ALLOW)
def test_ordinary_maker_text_with_numbers_still_passes(t):
    assert safety.scan(t) is None, repr(t)


def test_api_refuses_hidden_phone_number_with_contact_message():
    with pytest.raises(safety.ChatBlocked) as e:
        safety.check(f"Benchy remix 555{Z}123{Z}4567", "showcase title")
    assert e.value.status == 422 and e.value.payload["code"] == "contact_blocked"
    assert e.value.payload["message"] == safety.CONTACT_MESSAGE


def test_grooming_layer_and_underage_report_reason_untouched():
    assert safety.scan_grooming("how old are you") == "language"
    from app.community import moderation
    assert "underage_user" in moderation.REASONS
