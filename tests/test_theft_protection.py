"""Theft protection: geometry fingerprint + duplicate hold, 3MF owner tag, first-posted date,
view-only downloads, one-tap 'Report as stolen'."""
import io
import json
import zipfile

import numpy as np
import pytest
import trimesh

from app import config
from app.community import fingerprint as fp, protect
from app.community.store import ENGAGEMENT, LISTINGS, MODERATION, PREFS
from tests.b1 import client, photo_build

ADMIN = {"X-Admin-Token": "t0k"}


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(config, "DUPLICATE_CHECK", True)
    snap = {s: s.read() for s in (LISTINGS, ENGAGEMENT, PREFS, MODERATION, protect.FINGERPRINTS)}
    LISTINGS.write([])                 # other files leave projects made from the same sample photo behind
    protect.FINGERPRINTS.write({})
    yield
    for s, was in snap.items():
        s.write(was)


def U(n):
    return client({"display_name": n, "dob": "1990-01-01"})


def pub(c, title="Thing", **extra):
    body = {"build_id": photo_build(c), "title": title, "description": "d", "tags": ["x"], "accept_guidelines": True,
            "nsfw": False, "visibility": "public", "license_id": "cc-by-4.0", **extra}
    return c.post("/api/showcase", json=body)


# ---------------- fingerprint unit ----------------
def _shape():
    return trimesh.util.concatenate([trimesh.creation.box((10, 20, 30)),
                                     trimesh.creation.icosphere(2, radius=8).apply_translation((0, 0, 20))])


def _fp(mesh, tmp_path, name="m.stl"):
    p = tmp_path / name
    mesh.export(p)
    return fp.compute(p)


def test_fingerprint_invariant_to_rename_scale_move_rotate(tmp_path):
    a = _fp(_shape(), tmp_path, "a.stl")
    m = _shape()
    m.apply_scale(3.7)
    m.apply_transform(trimesh.transformations.rotation_matrix(1.1, [0.3, 0.5, 0.8]))
    m.apply_translation((120, -40, 7))
    b = _fp(m, tmp_path, "renamed_totally_different.3mf")
    s = fp.similar(a, b)
    assert s and s["score"] > 0.5


def test_fingerprint_near_match_survives_tiny_noise(tmp_path):
    a = _fp(_shape(), tmp_path, "a.stl")
    m = _shape()
    m.vertices = m.vertices + np.random.default_rng(1).normal(0, 0.01, m.vertices.shape)
    b = _fp(m, tmp_path, "b.stl")
    assert a["exact"] != b["exact"]
    assert fp.similar(a, b)


def test_fingerprint_rejects_different_shapes(tmp_path):
    a = _fp(_shape(), tmp_path, "a.stl")
    assert fp.similar(a, _fp(trimesh.creation.icosphere(3), tmp_path, "s.stl")) is None
    assert fp.similar(a, _fp(trimesh.creation.cylinder(5, 40), tmp_path, "c.stl")) is None
    m = _shape()
    m.apply_scale((1, 1, 2.5))                               # non-uniform stretch is a different shape
    assert fp.similar(a, _fp(m, tmp_path, "st.stl")) is None


def test_bad_file_has_no_fingerprint(tmp_path):
    (tmp_path / "x.stl").write_bytes(b"not a mesh")
    assert fp.safe_compute(tmp_path / "x.stl") is None


# ---------------- duplicate hold ----------------
def test_copy_of_remix_off_model_is_refused_not_held():
    """Re-upload protection (Oct 2026) replaces the old moderator hold for shares: remixes off -> refused, kept privately."""
    a, b = U("Orig"), U("Thief")
    src = pub(a, "Original", allow_remixes=False).json()
    r = pub(b, "Totally mine")
    assert r.status_code == 409
    j = r.json()
    assert j["code"] == "copy_refused" and j["original"]["share_url"] == f"/p/{src['id']}" and j["can_keep_private"]
    assert not any(x["title"] == "Totally mine" for x in LISTINGS.read())
    assert pub(b, "Just for me", visibility="private").status_code == 200       # private keep is fine


def test_owner_reupload_passes_with_warning():
    a = U("Self")
    pub(a, "v1")
    j = pub(a, "v2").json()
    assert not j.get("held_for_review")
    assert j["warnings"] and "your project" in j["warnings"][0]


def test_credited_remix_passes_uncredited_copy_gets_offer():
    a, b, c = U("RA"), U("RB"), U("RC")
    src = pub(a, "Src").json()
    assert pub(b, "Remix", remix_of=src["id"]).status_code == 200
    r = pub(c, "No credit")
    assert r.status_code == 409 and r.json()["code"] == "remix_offer"


def test_check_can_be_disabled(monkeypatch):
    monkeypatch.setattr(config, "DUPLICATE_CHECK", False)
    a, b = U("D1"), U("D2")
    pub(a)
    assert pub(b).status_code == 200


# ---------------- owner tag, first posted, view only ----------------
def test_downloaded_3mf_carries_owner_tag_and_first_posted():
    a, b = U("Tagger"), U("Getter")
    src = pub(a, "Tagged").json()
    seen = b.get(f"/api/showcase/{src['id']}").json()
    assert seen["first_posted"] == src["created"][:10]
    f3 = next(f for f in seen["files"] if f["name"].endswith(".3mf"))
    r = b.get(f3["url"])
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    model = z.read("3D/3dmodel.model").decode()
    assert 'name="zeim:ModelId">' + src["id"] in model and "xmlns:zeim=" in model
    assert f"/p/{src['id']}</metadata>" in model and src["created"][:10] in model
    meta = json.loads(z.read("Metadata/zeim_owner.json"))
    assert meta["ModelId"] == src["id"] and meta["CreatorHandle"].startswith("@")
    trimesh.load(io.BytesIO(r.content), file_type="3mf")      # still a valid 3MF


def test_tag_3mf_is_idempotent_and_safe():
    m = {"Title": "T", "zeim:ModelId": "abc"}
    raw = trimesh.creation.box().export(file_type="3mf")
    once = protect.tag_3mf(raw, m)
    twice = protect.tag_3mf(once, m)
    assert zipfile.ZipFile(io.BytesIO(twice)).read("3D/3dmodel.model").decode().count('name="zeim:ModelId"') == 1
    assert protect.tag_3mf(b"garbage", m) == b"garbage"


def test_view_only_enforced_server_side():
    a, b = U("VO"), U("VO2")
    src = pub(a, "Look", view_only="yes").json()
    name = src["files"][0]["name"]
    assert src["view_only"] and src["files"][0]["url"]                    # owner still gets files
    seen = b.get(f"/api/showcase/{src['id']}").json()
    assert seen["download_blocked"] and all(f["url"] is None for f in seen["files"])
    r = b.get(f"/api/showcase/{src['id']}/files/{name}")
    assert r.status_code == 403 and "view only" in r.json()["detail"]
    assert a.get(f"/api/showcase/{src['id']}/files/{name}").status_code == 200
    assert b.put(f"/api/showcase/{src['id']}/download", json={"view_only": False}).status_code == 404
    assert a.put(f"/api/showcase/{src['id']}/download", json={"view_only": False}).json()["view_only"] is False
    assert b.get(f"/api/showcase/{src['id']}/files/{name}").status_code == 200


# ---------------- report as stolen ----------------
def test_report_as_stolen_links_original(monkeypatch):
    a, b, c = U("SOrig"), U("SCopy"), U("SReporter")
    src = pub(a, "First").json()
    monkeypatch.setattr(config, "DUPLICATE_CHECK", False)                  # let the copy go live (e.g. it slipped past)
    cp = pub(b, "Copy").json()
    r = c.post(f"/api/showcase/{cp['id']}/report-stolen", json={})
    assert r.status_code == 200
    j = r.json()
    assert j["original_url"] == f"/p/{src['id']}" and j["dmca_url"] == "/legal/takedown"
    rep = next(x for x in MODERATION.read()["reports"] if x["id"] == j["id"])
    assert rep["reason"] == "stolen" and src["id"] in rep["details"]
    assert c.get(f"/api/showcase/{cp['id']}").status_code == 200            # never auto-hidden


def test_report_as_stolen_with_pasted_link_and_unknown_original():
    a, b = U("PL1"), U("PL2")
    it = pub(a, "Lone").json()
    j = b.post(f"/api/showcase/{it['id']}/report-stolen", json={"original_url": "https://example.com/thing/1"}).json()
    assert j["original_url"] == "https://example.com/thing/1"
    j2 = U("PL3").post(f"/api/showcase/{it['id']}/report-stolen").json()
    assert j2["original_url"] is None and j2["status"] == "open"
