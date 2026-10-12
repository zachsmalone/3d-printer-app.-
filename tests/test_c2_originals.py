"""Originals-first Showcase: the ZEIM Originals from library/originals replace the old EXAMPLE seed cards.
Tests use the 6-item fixture in tests/fixtures/originals (the real 378 MB library is not in git); one test checks the real
manifest when it is present on this machine. Kenji's hiding rules are checked on the server: lists, item pages, thumbs, files."""
import json, os
from pathlib import Path
import pytest
from app import config
from app.community import catalog
from tests.b1 import client, make_class, student, ADULT

WILD = {"zo-owl-whistle", "zo-open-reed-predator-call"}
CLASS_ONLY = {"zo-horn-dino-band-popper", "zo-fish-bottle-opener"}
ALL = WILD | CLASS_ONLY | {"zo-pencil-cup", "zo-gear-demo"}


def _ids(c, **params):
    return {i["id"] for i in c.get("/api/showcase", params={"tab": "free", **params}).json()["items"] if i.get("original")}


def _class_student():
    t, code, pw = make_class(); s = student(code, pw, "Otter")
    t.put(f"/api/classrooms/{code}/showcase", json={"enabled": True})
    return s


def test_originals_replace_the_example_cards_and_carry_credit_difficulty_fdm_untested_and_caveats():
    items = client().get("/api/showcase?tab=free").json()["items"]
    assert not [i for i in items if i.get("example")]                         # the 9 invented EXAMPLE cards are gone
    o = {i["id"]: i for i in items if i.get("original")}
    assert set(o) == ALL
    i = o["zo-pencil-cup"]
    assert i["credit"]["credit_line"] == '"Pencil Cup" by ZEIM · CC BY 4.0'
    assert i["difficulty"] == "Easy" and i["printer_suggested"] == "FDM" and i["untested"] is True
    assert "PLA" in i["material"] and i["caveats"] and i["category"] == "Containers"
    assert i["likes"] is None or i["likes"] == 0                                # no invented numbers
    assert i["thumb"] and i["files"][0]["name"] == "pencil-cup.stl"


def test_the_stl_download_and_preview_really_serve_the_library_files():
    c = client()
    f = c.get("/api/showcase/zo-pencil-cup").json()["files"][0]
    r = c.get(f["url"])
    assert r.status_code == 200 and r.content == (config.ORIGINALS / "pencil-cup.stl").read_bytes()
    assert c.get("/api/showcase/zo-pencil-cup/thumb").headers["content-type"] == "image/png"
    assert c.get("/api/showcase/zo-pencil-cup/files/..%2Foriginals_manifest.json").status_code == 404
    assert c.get("/api/showcase/zo-pencil-cup/files/gear-demo.stl").status_code == 404   # only the item's own file


def test_category_filter_and_category_list():
    c = client()
    r = c.get("/api/showcase?tab=free").json()
    assert {"Wildlife Calls", "Containers", "School STEM"} <= set(r["categories"])
    assert _ids(c, category="Wildlife Calls") == WILD
    assert _ids(c, category="Containers") == {"zo-pencil-cup"}


def test_class_students_never_get_wildlife_calls_or_the_popper_and_bottle_opener():
    s = _class_student()
    assert _ids(s) == ALL - WILD - CLASS_ONLY
    assert "Wildlife Calls" not in s.get("/api/showcase?tab=free").json()["categories"]
    assert _ids(s, category="Wildlife Calls") == set()
    for iid in WILD | CLASS_ONLY:                                               # item page, thumb and file all look like 404
        assert s.get(f"/api/showcase/{iid}").status_code == 404
        assert s.get(f"/api/showcase/{iid}/thumb").status_code == 404
        slug = iid[3:]
        assert s.get(f"/api/showcase/{iid}/files/{slug}.stl").status_code == 404
    assert _ids(client(ADULT)) == ALL                                           # adults still see everything


def test_under_13_viewers_lose_wildlife_calls_but_keep_the_popper_and_bottle_opener(monkeypatch):
    from app.community.identity import Actor
    a = Actor(sid="u13-test", user={"dob": "2017-03-03"})
    items = {i["id"] for i in catalog.list_items(a, "free") if i.get("original")}
    assert items == ALL - WILD
    with pytest.raises(catalog.Denied):
        catalog.get("zo-owl-whistle", a)


def test_missing_library_means_no_originals_not_a_crash(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ORIGINALS", tmp_path / "nothing")
    r = client().get("/api/showcase?tab=free")
    assert r.status_code == 200 and not [i for i in r.json()["items"] if i.get("original")]


REAL = Path(__file__).resolve().parent.parent / "library" / "originals"
for _p in (REAL, Path("/workspace/photo3d/library/originals")):
    if (_p / "originals_manifest.json").exists():
        REAL = _p; break


@pytest.mark.skipif(not (REAL / "originals_manifest.json").exists(), reason="real ZEIM Originals library not installed here (it is not in git)")
def test_the_real_library_gives_45_originals_with_files_and_wildlife_calls_hidden_for_students(monkeypatch):
    monkeypatch.setattr(config, "ORIGINALS", REAL)
    m = json.loads((REAL / "originals_manifest.json").read_text())
    c = client()
    o = [i for i in c.get("/api/showcase?tab=free").json()["items"] if i.get("original")]
    assert len(o) == len(m["models"]) == 45
    assert all(i["files"] and i["thumb"] and i["untested"] and i["credit"]["credit_line"].endswith("by ZEIM · CC BY 4.0") for i in o)
    wild = {i["id"] for i in o if i["category"] == "Wildlife Calls"}
    assert "zo-open-reed-predator-call" in wild and len(wild) == 12
    s = _class_student()
    seen = _ids(s)
    assert not (seen & wild) and not (seen & CLASS_ONLY) and len(seen) == 45 - 12 - 2

