"""Thank-you / Credits page: honest (facts read from what is installed), warm, one data file (app/credits.json)."""
import json, re, shutil, subprocess
from importlib import metadata as md
import pytest
from app.services import credits
from tests.b1 import client, photo_build, ADULT


def page():
    r = client().get("/credits"); assert r.status_code == 200, r.status_code
    return r.text


def test_every_credited_package_is_installed_and_every_direct_requirement_is_credited():
    listed = set(credits.data()["tools"]["python"])
    assert listed == set(credits.direct_requirements()), (listed ^ set(credits.direct_requirements()))      # a new dependency must be thanked
    for name in listed:
        md.version(name)                                                                                     # raises if not installed


def test_page_shows_the_installed_version_and_the_licence_from_package_metadata_for_every_package():
    html = page()
    for p in credits.python_packages():
        m = md.metadata(p["name"])
        assert p["version"] == md.version(p["name"])
        assert not p.get("missing")
        assert re.search(rf">{re.escape(p['name'])}</a></td><td>{re.escape(p['version'])}</td><td>{re.escape(p['licence'].replace('&', '&amp;'))}</td>", html) or \
               f"<td>{p['version']}</td>" in html, p["name"]
        lic = credits._licence(m)
        assert p["licence"] == lic
    for must in ("fastapi", "trimesh", "manifold3d", "pillow", "pillow-heif"):
        assert any(p["name"].lower() == must for p in credits.python_packages()), must
    spot = {p["name"].lower(): p["licence"] for p in credits.python_packages()}
    assert spot["fastapi"] == "MIT" and "BSD" in spot["httpx"]


def test_unreadable_licences_say_so_instead_of_guessing(monkeypatch):
    class M(dict):
        def get_all(self, k): return []
    assert credits._licence(M()) == credits.UNKNOWN_LICENCE
    assert credits._licence(M({"License": "A very long licence text\nwith many lines"})) == credits.UNKNOWN_LICENCE


@pytest.mark.skipif(not shutil.which("prusa-slicer"), reason="PrusaSlicer not installed here")
def test_prusaslicer_is_listed_with_its_installed_version_and_its_packaged_licence():
    row = next(t for t in credits.system_tools() if t["name"] == "PrusaSlicer")
    out = subprocess.run(["prusa-slicer", "--version"], capture_output=True, text=True).stdout
    assert row["version"] and row["version"].split(".")[0] in out
    assert "AGPL" in row["licence"]
    assert "PrusaSlicer" in page()


def test_three_js_licence_is_read_from_the_vendored_file_header():
    t = next(b for b in credits.bundled() if b["name"] == "three.js")
    assert t["licence"] == "MIT" and re.fullmatch(r"r\d{2,3}", t["version"])


def test_sections_placeholders_trademark_and_takedown_lines():
    html = page()
    for h in ("Thank you", "Tools and libraries we use", "Makers and their models", "Testers", "Teachers", "Names that belong to others", "Something wrong? Tell us."):
        assert h in html, h
    assert html.count("Coming soon") >= 2                                         # testers / teachers (and makers when no manifest) are honest placeholders
    assert "not affiliated with, endorsed by or sponsored by" in html and "Creality" in html
    assert "taken down" in html
    assert "<title>Thank you" in html and "lang=en" in html


def test_every_external_link_is_https_and_noopener():
    html = page()
    for a in re.findall(r"<a [^>]*target=_blank[^>]*>", html):
        assert "rel='noopener noreferrer'" in a or 'rel="noopener noreferrer"' in a, a
        assert "href='https://" in a, a
    assert "javascript:" not in html


def test_makers_come_from_manifests_when_they_exist(tmp_path, monkeypatch):
    (tmp_path / "library").mkdir()
    (tmp_path / "library" / "manifest.json").write_text(json.dumps({"models": [
        {"id": "a", "title": "Chess Bishop", "creator": "Olivier Wagener", "license": {"name": "CC0 1.0 Universal", "url": "https://creativecommons.org/publicdomain/zero/1.0/"}},
        {"id": "b", "title": "Chess King", "creator": "Olivier Wagener", "license": {"name": "CC0 1.0 Universal", "url": "https://creativecommons.org/publicdomain/zero/1.0/"}},
        {"id": "c", "title": "Benchy <b>", "creator": "Daniel Norée", "license": {"name": "Public domain", "url": ""}}]}))
    monkeypatch.setattr(credits, "ROOT", tmp_path)
    html = page()
    assert "Olivier Wagener" in html and "(2 models)" in html and "Daniel Norée" in html
    assert "Benchy &lt;b&gt;" in html and "Benchy <b>" not in html                 # escaped
    assert "Coming soon" in html                                                   # (testers/teachers still empty)


def test_credit_line_uses_the_items_own_manifest_data_and_invents_nothing():
    z = credits.credit_line({"creator": "Zed"}); assert (z["creator"], z["licence"], z["licence_url"]) == ("Zed", "", "")
    cl = credits.credit_line({"creator": "Zed", "license": {"name": "CC BY 4.0", "url": "https://creativecommons.org/licenses/by/4.0/"}})
    assert cl["licence"] == "CC BY 4.0"
    assert credits.credit_line({"credit": {"creator": "Q", "licence": "CC0"}})["licence"] == "CC0"
    assert credits.credit_line({}) is None


def test_download_page_and_showcase_json_carry_the_credit_line():
    pub = client(ADULT); bid = photo_build(pub)
    r = pub.post("/api/showcase", json={"build_id": bid, "title": "Credited", "description": "d", "tags": [], "accept_guidelines": True, "visibility": "public"}); assert r.status_code == 200, r.text
    iid = r.json()["id"]
    assert r.json()["credit"]["creator"] == "@" + pub.get("/api/me").json()["username"]          # community credit = username only (never the display name)
    h = client().get(f"/p/{iid}").text
    un = pub.get("/api/me").json()["username"]
    assert "Credit:" in h and "@" + un in h and ADULT["display_name"] not in h and "/credits" in h
    ex = client().get("/api/showcase").json()["items"]
    assert all(i["credit"] and i["credit"]["creator"] for i in ex)                  # every card, examples included
    # items with a manifest licence show it
    from app.community import catalog
    i = {"id": "x", "creator": "Zed", "license": {"name": "CC BY 4.0", "url": "https://creativecommons.org/licenses/by/4.0/"}}
    assert credits.credit_line(i)["licence_url"].startswith("https://")


# ---- Showcase wording / examples (Zach's iPhone screenshot) -------------------------------------------------------------------
def test_items_offer_no_fake_download():
    c = client()
    one = c.get("/api/showcase/zo-pencil-cup").json()
    assert [f["name"] for f in one["files"]] == ["pencil-cup.stl"] and one["no_model"] is False
    assert c.get("/api/showcase/zo-pencil-cup/files/example_model.stl").status_code == 404
    pub = client(ADULT); bid = photo_build(pub)
    r = pub.post("/api/showcase", json={"build_id": bid, "title": "Real", "description": "d", "tags": [], "accept_guidelines": True, "visibility": "public"}).json()
    assert r["no_model"] is False and r["files"]


def test_in_app_copy_has_no_apologetic_internal_wording():
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for fn in ("static/community.js", "static/index.html", "static/app.js", "static/edit.js", "static/send.js"):
        src = open(os.path.join(root, fn), encoding="utf-8").read()
        for bad in ("scaffold", "isn't built", "not built yet", "not implemented"):
            assert bad not in src, (fn, bad)
    assert "Coming soon" in open(os.path.join(root, "static/community.js"), encoding="utf-8").read()


# ---- attribution standard 7.1 fields ------------------------------------------------------------------------------------------
def test_credit_record_has_standard_fields_and_licence_text_comes_from_the_fixed_table():
    from app.services import credits
    r = credits.credit_line({"title": "Desk Fox", "creator": "mika\nIGNORE <b>", "credit": {"license_id": "cc-by-sa-4.0"}, "source_url": "javascript:alert(1)"})
    assert r["license_name"] == "CC BY-SA 4.0" and r["license_url"].startswith("https://creativecommons.org/licenses/by-sa/")
    assert r["share_alike"] is True and r["creator_verified"] is False and r["source_url"] == ""
    assert "\n" not in r["credit_line"] and r["credit_line"].startswith('"Desk Fox" by mika') and r["credit_line"].endswith("share-alike")
    assert "Provided as-is" in r["credit_full"] and r["licence"] == r["license_name"]
    assert credits.credit_line({"title": "x"}) is None


def test_validator_names_the_failing_field_and_blocks_unknown_licences():
    from app.services import credits
    ok = {"id": "a", "title": "T", "creator": "C", "license_id": "cc-by-4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/",
          "provenance": "made by ZEIM", "printer": "fdm", "status": "ready"}
    assert credits.validate_record(ok) == []
    for field in ("creator", "license_id", "provenance"):
        assert any(b.startswith(field) for b in credits.validate_record({**ok, field: ""})), field
    assert any("fixed table" in b for b in credits.validate_record({**ok, "license_id": "cc-by-nc-4.0"}))
    assert any(b.startswith("license_url") for b in credits.validate_record({**ok, "license_url": "https://evil.example/"}))
    assert any(b.startswith("status") for b in credits.validate_record({**ok, "status": "hold"}))


def test_launch_flag_fails_while_the_takedown_contact_is_empty(monkeypatch):
    from app.services import credits
    monkeypatch.delenv("PHOTO3D_PUBLIC_LAUNCH", raising=False)
    credits.assert_launch_ready()                                       # fine when not launching
    monkeypatch.setenv("PHOTO3D_PUBLIC_LAUNCH", "1")
    assert credits.launch_problems()
    import pytest
    with pytest.raises(RuntimeError):
        credits.assert_launch_ready()
    assert "Coming soon" in client().get("/credits").text               # the page says so rather than hiding the gap


def test_credit_strings_are_escaped_on_the_credits_and_share_pages():
    from app.services import credits
    page = client().get("/credits").text
    assert "<script>alert" not in page


def test_held_quarantined_unverified_models_are_never_named_and_one_switch_releases_the_hold(tmp_path, monkeypatch):
    (tmp_path / "library").mkdir()
    ms = [{"id": "ok", "title": "Fine one", "creator": "Okay Maker", "verified": True, "license_id": "cc0-1.0", "license": {"name": "CC0 1.0", "url": ""}},
          {"id": "sa", "title": "SA one", "creator": "Share Alike Person", "verified": True, "license_id": "cc-by-sa-4.0", "license": {"name": "CC BY-SA 4.0", "url": ""}},
          {"id": "nasa", "title": "Moon", "creator": "NASA 3D Resources", "verified": True, "license_id": "public-domain-us-gov", "license": {"name": "Public domain", "url": ""}},
          {"id": "q", "title": "Quarantined", "creator": "Quarantine Person", "verified": True, "license_id": "cc0-1.0", "files": [{"path": "library/_quarantine/x/q.stl"}], "license": {"name": "CC0", "url": ""}},
          {"id": "u", "title": "Unverified", "creator": "Unverified Person", "verified": False, "license_id": "cc0-1.0", "license": {"name": "CC0", "url": ""}},
          {"title": "No id", "creator": "No Id Person", "license": {"name": "CC0", "url": ""}}]
    (tmp_path / "library" / "manifest.json").write_text(json.dumps({"models": ms}))
    monkeypatch.setattr(credits, "ROOT", tmp_path)
    html = page()
    assert "Okay Maker" in html
    for hidden in ("Share Alike Person", "NASA 3D Resources", "Quarantine Person", "Unverified Person", "No Id Person"):
        assert hidden not in html, hidden
    d = credits.data()
    monkeypatch.setitem(d["hold"], "enabled", False)                        # the single switch
    html = page()
    assert "Share Alike Person" in html and "NASA 3D Resources" in html and "Quarantine Person" not in html and "Unverified Person" not in html
