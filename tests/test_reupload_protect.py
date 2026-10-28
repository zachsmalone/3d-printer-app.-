"""Re-upload protection: a model downloaded from another maker's Showcase can't be re-shared as your own.
Shape fingerprint (moved / rotated / scaled / mirrored / re-meshed copies), remix-offer vs refusal, own models pass,
private keep, visibility re-check, owner 'Report a copy', admin review list, origin tag in downloads."""
import glob
import hashlib
import io
import itertools
import os
import zipfile

import numpy as np
import pytest
import trimesh
from PIL import Image, ImageDraw

from app import config
from app.community import fingerprint as fp, protect
from app.community.store import ENGAGEMENT, LISTINGS, MODERATION, PREFS
from tests.b1 import client, gen, photo_build

ADMIN = {"X-Admin-Token": "t0k"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE_STL = os.path.join(ROOT, "static", "sample_model.stl")


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(config, "DUPLICATE_CHECK", True)
    snap = {s: s.read() for s in (LISTINGS, ENGAGEMENT, PREFS, MODERATION, protect.FINGERPRINTS)}
    LISTINGS.write([])
    protect.FINGERPRINTS.write({})
    yield
    for s, was in snap.items():
        s.write(was)


def U(n):
    return client({"display_name": n, "dob": "1990-01-01"})


def pub(c, title="Thing", build=None, **extra):
    body = {"build_id": build or photo_build(c), "title": title, "description": "d", "tags": ["x"], "accept_guidelines": True,
            "nsfw": False, "visibility": "public", "license_id": "cc-by-4.0", **extra}
    return c.post("/api/showcase", json=body)


def _fpm(mesh, tmp_path, name="m.stl"):
    p = tmp_path / name
    mesh.export(p)
    return fp.compute(p)


def _sample():
    return trimesh.load(SAMPLE_STL, force="mesh")


def _t(kind):
    m = _sample()
    if kind == "moved":
        m.apply_translation((140, -55, 12))
    elif kind == "rotated":
        m.apply_transform(trimesh.transformations.rotation_matrix(2.3, [0.2, 0.9, 0.4]))
    elif kind == "scaled":
        m.apply_scale(0.42)
    elif kind == "mirrored":
        m.apply_transform(np.diag([1.0, -1.0, 1.0, 1.0]))   # trimesh re-winds faces after a reflection
    elif kind == "all":
        m.apply_transform(np.diag([-1.0, 1.0, 1.0, 1.0])); m.invert()   # mirrored AND inside-out normals
        m.apply_transform(trimesh.transformations.rotation_matrix(0.9, [1, 1, 0]))
        m.apply_scale(2.6); m.apply_translation((3, 4, 5))
    elif kind == "remeshed":
        m = m.subdivide()
    return m


# ---------------- fingerprint ----------------
@pytest.mark.parametrize("kind", ["exact", "moved", "rotated", "scaled", "mirrored", "all", "remeshed"])
def test_transformed_copies_match(kind, tmp_path):
    a = fp.compute(SAMPLE_STL)
    b = _fpm(_t(kind), tmp_path, f"{kind}.stl")
    s = fp.similar(a, b)
    assert s, kind
    if kind == "exact":
        assert s["exact"]


def _distinct_meshes(tmp_path):
    """All sample + test meshes in the repo (byte-identical files counted once) plus a few primitives."""
    out, seen = {}, set()
    for f in sorted(glob.glob(os.path.join(ROOT, "tests", "fixtures", "**", "*.stl"), recursive=True)) + [SAMPLE_STL]:
        h = hashlib.sha256(open(f, "rb").read()).hexdigest()
        if h not in seen:
            seen.add(h)
            out[os.path.relpath(f, ROOT)] = fp.compute(f)
    prims = {"box": trimesh.creation.box((10, 20, 30)), "sphere": trimesh.creation.icosphere(3),
             "cyl": trimesh.creation.cylinder(5, 40), "capsule": trimesh.creation.capsule(20, 5),
             "cone": trimesh.creation.cone(5, 20), "slab": trimesh.creation.box((50, 50, 3))}
    for k, m in prims.items():
        out[k] = _fpm(m, tmp_path, k + ".stl")
    return out


def test_no_false_positives_across_sample_and_test_meshes(tmp_path):
    fps = _distinct_meshes(tmp_path)
    assert len(fps) >= 8
    hits = [(a, b) for a, b in itertools.combinations(fps, 2) if fp.similar(fps[a], fps[b])]
    assert hits == []


def _img(path, kind):
    im = Image.new("L", (240, 180), 40)
    d = ImageDraw.Draw(im)
    if kind == "circles":
        for k in range(6):
            d.ellipse((20 + k * 30, 30 + k * 10, 70 + k * 30, 80 + k * 10), fill=230)
    elif kind == "bars":
        for k in range(0, 240, 24):
            d.rectangle((k, 0, k + 10, 180), fill=200)
    else:
        for y in range(180):
            d.line((0, y, 240, y), fill=int(40 + y))
    b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()


def test_different_photo_reliefs_do_not_match():
    """Photo reliefs share an outline (a plate), so this is the realistic false-positive risk."""
    c = U("Reliefs")
    fps = []
    for k in ("circles", "bars", "ramp"):
        r = gen(c, data=_img(None, k), name=f"{k}.png")
        assert r.status_code == 200, r.text
        fps.append(fp.compute(config.OUT / r.json()["id"] / "model.stl"))
    for a, b in itertools.combinations(fps, 2):
        assert fp.similar(a, b) is None


def test_old_fingerprints_without_voxels_still_compare(tmp_path):
    a = fp.compute(SAMPLE_STL)
    b = dict(a); b.pop("vox")
    assert fp.similar(a, b)["exact"]
    c = _fpm(_t("remeshed"), tmp_path); c.pop("vox")
    assert fp.similar(a, c) is None                        # re-mesh matching needs the voxel grid on both sides


# ---------------- share policy (API) ----------------
def _with_mesh(monkeypatch, tmp_path, kind):
    """Make the NEXT publish fingerprint as a transformed copy of the sample model."""
    _fake(monkeypatch, _fpm(_t(kind), tmp_path, f"up_{kind}.stl"))


_REAL = fp.safe_compute


def _fake(monkeypatch, f):
    """Only uploads get the fake fingerprint; ZEIM Originals keep their real one."""
    monkeypatch.setattr(fp, "safe_compute", lambda p: _REAL(p) if str(config.ORIGINALS) in str(p) else f)


@pytest.mark.parametrize("kind", ["exact", "moved", "rotated", "scaled", "mirrored"])
def test_reupload_of_remix_off_model_is_refused(kind, monkeypatch, tmp_path):
    a, b = U("Maker" + kind), U("Other" + kind)
    _with_mesh(monkeypatch, tmp_path, "exact")
    src = pub(a, "Original", allow_remixes=False).json()
    _with_mesh(monkeypatch, tmp_path, kind)
    r = pub(b, "Mine now")
    assert r.status_code == 409, r.text
    j = r.json()
    assert j["code"] == "copy_refused" and j["original"]["id"] == src["id"]
    assert "Sorry" in j["detail"] and "Private" in j["detail"] and "remixes off" in j["detail"]
    assert not any(x["title"] == "Mine now" for x in LISTINGS.read())
    k = pub(b, "Kept", visibility="private")                         # still fine to keep privately
    assert k.status_code == 200 and k.json()["visibility"] == "private"
    kid = k.json()["id"]
    v = b.put(f"/api/showcase/{kid}/visibility", json={"visibility": "public"})     # can't be flipped public later
    assert v.status_code == 409 and v.json()["code"] == "copy_refused"


def test_reupload_of_remixable_model_gets_credit_offer_then_posts_as_remix(monkeypatch, tmp_path):
    a, b = U("Remixable"), U("Taker")
    _with_mesh(monkeypatch, tmp_path, "exact")
    src = pub(a, "Open one").json()
    _with_mesh(monkeypatch, tmp_path, "rotated")
    r = pub(b, "Mine")
    assert r.status_code == 409
    j = r.json()
    assert j["code"] == "remix_offer" and j["original"]["share_url"] == f"/p/{src['id']}" and "credited remix" in j["detail"]
    r2 = pub(b, "Mine, credited", remix_of="http://x/p/" + src["id"])
    assert r2.status_code == 200, r2.text
    assert b.get(f"/api/showcase/{r2.json()['id']}").json()["remix_chain"][0]["id"] == src["id"]


def test_visibility_flip_accepts_credit(monkeypatch, tmp_path):
    a, b = U("VA"), U("VB")
    _with_mesh(monkeypatch, tmp_path, "exact")
    src = pub(a, "Src").json()
    kid = pub(b, "Private copy", visibility="private").json()["id"]
    assert b.put(f"/api/showcase/{kid}/visibility", json={"visibility": "public"}).json()["code"] == "remix_offer"
    ok = b.put(f"/api/showcase/{kid}/visibility", json={"visibility": "public", "remix_of": src["id"]})
    assert ok.status_code == 200 and ok.json()["visibility"] == "public"


def test_own_model_passes(monkeypatch, tmp_path):
    a = U("SelfMaker")
    _with_mesh(monkeypatch, tmp_path, "exact")
    pub(a, "v1", allow_remixes=False)
    _with_mesh(monkeypatch, tmp_path, "mirrored")
    r = pub(a, "v2")
    assert r.status_code == 200 and r.json()["warnings"], r.text


def test_private_work_of_others_is_never_compared(monkeypatch, tmp_path):
    a, b = U("PrivA"), U("PrivB")
    _with_mesh(monkeypatch, tmp_path, "exact")
    pub(a, "Secret", visibility="private", allow_remixes=False)
    assert pub(b, "Same shape").status_code == 200                     # nothing about a private project leaks


def test_different_model_passes(monkeypatch, tmp_path):
    a, b = U("DA"), U("DB")
    _with_mesh(monkeypatch, tmp_path, "exact")
    pub(a, "Sample", allow_remixes=False)
    other = _fpm(trimesh.creation.icosphere(3), tmp_path, "sp.stl")
    _fake(monkeypatch, other)
    assert pub(b, "Sphere").status_code == 200


# ---------------- owner 'Report a copy' + admin list ----------------
def test_owner_report_a_copy_and_admin_review_list(monkeypatch, tmp_path):
    a, b, c = U("OwnerR"), U("CopierR"), U("Stranger")
    _with_mesh(monkeypatch, tmp_path, "exact")
    src = pub(a, "Mine first").json()
    monkeypatch.setattr(config, "DUPLICATE_CHECK", False)               # a copy slipped past (e.g. check was off)
    cp = pub(b, "Copy").json()
    found = a.get(f"/api/showcase/{src['id']}/copies").json()["copies"]
    assert [x["id"] for x in found] == [cp["id"]]
    assert c.get(f"/api/showcase/{src['id']}/copies").status_code == 404    # owner only
    assert c.post(f"/api/showcase/{src['id']}/report-copy", json={"copy_url": cp["id"]}).status_code == 404
    r = a.post(f"/api/showcase/{src['id']}/report-copy", json={"copy_url": f"https://zeim.app/p/{cp['id']}"})
    assert r.status_code == 200, r.text
    assert a.post(f"/api/showcase/{src['id']}/report-copy", json={"copy_url": src["id"]}).status_code == 422
    q = a.get("/api/moderation/copies", headers=ADMIN).json()["reports"]
    rep = next(x for x in q if x["id"] == r.json()["id"])
    assert rep["item_id"] == cp["id"] and rep["original_id"] == src["id"] and rep["by_owner"] and rep["original_preview"]
    assert a.get("/api/moderation/copies").status_code in (401, 403)
    assert c.get(f"/api/showcase/{cp['id']}").status_code == 200        # never auto-hidden


def _download_3mf(c, item):
    seen = c.get(f"/api/showcase/{item['id']}").json()
    f3 = next(f for f in seen["files"] if f["name"].endswith(".3mf"))
    r = c.get(f3["url"])
    assert r.status_code == 200, r.text
    return r.content


def _plant(bid, blob):
    from app.services.history import store
    p = store.dir(bid) / "original.3mf"
    p.write_bytes(blob)


def _no_shape(monkeypatch):
    """Shape check misses. The owner tag is the only signal."""
    monkeypatch.setattr(fp, "safe_compute", lambda p: None)


def test_owner_tag_blocks_reupload_when_the_shape_check_misses(monkeypatch):
    a, b = U("TagA"), U("TagB")
    src = pub(a, "Keep off", allow_remixes=False).json()
    blob = _download_3mf(a, src)
    _no_shape(monkeypatch)
    assert pub(b, "Different shape").status_code == 200
    bid = photo_build(b)
    _plant(bid, blob)
    r = pub(b, "Stolen file", build=bid)
    assert r.status_code == 409, r.text
    j = r.json()
    assert j["code"] == "copy_refused" and j["original"]["id"] == src["id"]
    assert not any(x["title"] == "Stolen file" for x in LISTINGS.read())


def test_owner_tag_on_a_remixable_model_offers_credit(monkeypatch):
    a, b = U("TagOpen"), U("TagTake")
    src = pub(a, "Open").json()
    blob = _download_3mf(a, src)
    _no_shape(monkeypatch)
    bid = photo_build(b)
    _plant(bid, blob)
    r = pub(b, "No credit", build=bid)
    assert r.status_code == 409 and r.json()["code"] == "remix_offer"
    ok = pub(b, "Credited", build=bid, remix_of=src["id"])
    assert ok.status_code == 200, ok.text
    assert b.get(f"/api/showcase/{ok.json()['id']}").json()["remix_chain"][0]["id"] == src["id"]


def test_owner_tag_of_a_private_project_is_not_revealed(monkeypatch):
    a, b = U("TagPriv"), U("TagStranger")
    src = pub(a, "Secret title", visibility="private", allow_remixes=False).json()
    raw = trimesh.creation.box().export(file_type="3mf")
    blob = protect.tag_3mf(raw, {"Title": "T", "zeim:ModelId": src["id"]})
    _no_shape(monkeypatch)
    bid = photo_build(b)
    _plant(bid, blob)
    r = pub(b, "Public anyway", build=bid)
    assert r.status_code == 200, r.text
    assert "Secret title" not in r.text


def test_own_tagged_file_passes_with_a_warning(monkeypatch):
    a = U("TagSelf")
    src = pub(a, "Mine first").json()
    blob = _download_3mf(a, src)
    _no_shape(monkeypatch)
    bid = photo_build(a)
    _plant(bid, blob)
    r = pub(a, "Mine again", build=bid)
    assert r.status_code == 200, r.text
    assert r.json()["warnings"] and "your project" in r.json()["warnings"][0]


def test_private_keep_of_a_tagged_file_cannot_be_flipped_public(monkeypatch):
    a, b = U("TagKeepA"), U("TagKeepB")
    src = pub(a, "Locked", allow_remixes=False).json()
    blob = _download_3mf(a, src)
    _no_shape(monkeypatch)
    bid = photo_build(b)
    _plant(bid, blob)
    kept = pub(b, "Kept", build=bid, visibility="private")
    assert kept.status_code == 200, kept.text
    kid = kept.json()["id"]
    v = b.put(f"/api/showcase/{kid}/visibility", json={"visibility": "public"})
    assert v.status_code == 409 and v.json()["code"] == "copy_refused" and v.json()["original"]["id"] == src["id"]
    ok = b.put(f"/api/showcase/{kid}/visibility", json={"visibility": "public", "remix_of": src["id"]})
    assert ok.status_code == 403 and "turned off remixes" in ok.text


def test_download_origin_tag_keeps_geometry():
    a, b = U("TagO"), U("TagD")
    src = pub(a, "Tagged").json()
    f3 = next(f for f in b.get(f"/api/showcase/{src['id']}").json()["files"] if f["name"].endswith(".3mf"))
    from app.community import catalog
    orig = catalog.LDIR / src["id"] / f3["name"]                        # the untagged file on disk
    got = b.get(f3["url"]).content
    assert got != orig.read_bytes()
    m = trimesh.load(io.BytesIO(got), file_type="3mf", force="mesh")
    m0 = trimesh.load(str(orig), force="mesh")
    assert len(m.faces) == len(m0.faces) and np.allclose(m.bounds, m0.bounds) and np.isclose(m.volume, m0.volume)
    assert "zeim:SourceURL" in zipfile.ZipFile(io.BytesIO(got)).read("3D/3dmodel.model").decode()
