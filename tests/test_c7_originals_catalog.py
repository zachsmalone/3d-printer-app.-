"""Originals catalog facts (2026-10-13): each ZEIM Original's Showcase page shows the REAL facts from the Originals manifest -
size, supports, kit parts, how to use it and assembly steps. A fact the manifest doesn't have (or has broken) is left out, never
guessed. Uses the 6-item fixture in tests/fixtures/originals; one test checks the real 45-item library when it is on this machine."""
import json
from pathlib import Path
import pytest
from app.community import catalog
from tests.b1 import client

JS = (Path(__file__).resolve().parent.parent / "static" / "community.js").read_text()


def _item(c, iid):
    r = c.get("/api/showcase/" + iid)
    assert r.status_code == 200
    return r.json()


def test_size_and_supports_come_straight_from_the_manifest():
    i = _item(client(), "zo-pencil-cup")
    assert i["size_mm"] == {"x": 70.0, "y": 70.0, "z": 90.0, "note": "bounding box of the printed part"}
    assert i["supports_level"] == "none" and "without supports" in i["supports_detail"]
    assert i["how_used"]                                       # already in the manifest, now shown on the page
    assert i["parts"] == [] and i["assembly_steps"] == []      # a single part: no kit list, no steps


def test_kit_parts_and_assembly_steps_are_listed_as_the_manifest_words_them():
    i = _item(client(), "zo-gear-demo")
    assert i["size_mm"]["x"] == 120.0 and i["size_mm"]["note"] == ""
    assert i["parts"] == [{"name": "big gear", "size_mm": [60.0, 60.0, 8.0]}, {"name": "small gear", "size_mm": [30.0, 30.0, 8.0]},
                          {"name": "base plate", "size_mm": [120.0, 80.0, 4.0]},
                          {"name": "crank", "about": "hand crank with a round knob"}]     # the broken "bad_part" row is dropped
    assert i["assembly_steps"] == ["1. Print the base and both gears.", "2) Press the gears onto the base pegs.", "3. Turn the big gear."]   # blank step dropped


def test_a_broken_or_missing_size_is_left_out_not_guessed():
    c = client()
    assert _item(c, "zo-owl-whistle")["size_mm"] is None                  # x = 0 in the manifest
    i = _item(c, "zo-fish-bottle-opener")                                 # no size / supports / parts at all
    assert i["size_mm"] is None and i["supports_detail"] == "" and i["parts"] == [] and i["assembly_steps"] == []


def test_list_cards_carry_the_same_facts_and_no_school_wording():
    r = client().get("/api/showcase?tab=free").json()
    o = {i["id"]: i for i in r["items"] if i.get("original")}
    assert o["zo-pencil-cup"]["size_mm"]["z"] == 90.0
    assert "School STEM" not in r["categories"] and "STEM & Science" in r["categories"]     # school features were removed 2026-10-12
    assert all("school" not in i["category"].lower() for i in o.values())
    assert {i["id"] for i in client().get("/api/showcase", params={"tab": "free", "category": "STEM & Science"}).json()["items"]} == {"zo-gear-demo"}


def test_community_projects_never_get_invented_original_facts():
    i = {"id": "x", "title": "t", "creator": "a", "creator_id": "u1", "tags": [], "mode": "relief", "description": "", "created": "2026-10-01T00:00:00+00:00",
         "files": [], "owner_sid": None, "visibility": "public", "hidden": False, "size_mm": {"x": 1, "y": 1, "z": 1}, "parts": [{"name": "p", "size_mm": [1, 1, 1]}]}
    from app.community.identity import Actor
    pub = catalog.public(i, Actor(sid="s", user=None))
    assert pub["size_mm"] is None and pub["parts"] == [] and pub["assembly_steps"] == [] and pub["supports_detail"] == ""


def test_the_detail_page_renders_the_facts_and_escapes_them():
    assert "const origMoreHTML" in JS and "origMoreHTML(i)" in JS
    for h in ("How to use it", "Parts in this kit", "Put it together", "Size:"):
        assert h in JS
    body = JS.split("const origMoreHTML", 1)[1].split("async function loadShowcase", 1)[0]
    assert "esc(i.how_used)" in body and "esc(t)" in body and "esc(p.name)" in body and "esc(p.about" in body and "esc(i.supports_detail)" in body


REAL = Path("/workspace/photo3d/library/originals/originals_manifest.json")


@pytest.mark.skipif(not REAL.is_file(), reason="real Originals library not installed on this machine")
def test_every_real_original_has_a_real_size_and_supports_note():
    m = json.loads(REAL.read_text())["models"]
    assert len(m) == 45
    for x in m:
        assert catalog._size(x) is not None, x["slug"]
        assert x.get("supports_detail"), x["slug"]
        if x.get("assembly_steps"):
            assert catalog._steps(x) == [t.strip() for t in x["assembly_steps"] if t.strip()][:12], x["slug"]
        if isinstance(x.get("parts"), dict):
            assert len(catalog._parts(x)) == len(x["parts"]), x["slug"]
