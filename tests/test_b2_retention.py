"""Build-file retention, favorites, the 20-build cap and the disk guard (Kenji's cleanup rules + Yami's approval).
Rules under test: starred builds are NEVER removed by age, by the cap, or by a low disk (only by their owner / 'Delete my stuff');
ordinary builds go after 7 days, builds shared or sent to a class after 30; cleanup only ever looks inside the per-build folder."""
import json, logging, os, shutil, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
from app import config
from app.services import retention
from app.services.history import store, BuildStore
from tests import b1
from tests.b1 import client, photo_build, ADULT


def _age(bid, days):
    m = store.get(bid); m["created"] = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(); store.save(m)


def _exists(bid): return (store.dir(bid) / "meta.json").exists()


def test_cap_rolls_off_the_oldest_unstarred_build_and_never_a_starred_one(monkeypatch):
    monkeypatch.setattr(store, "limit", 3)
    c = client(ADULT)
    a, b, d = (photo_build(c) for _ in range(3))
    _age(a, 3); _age(b, 2); _age(d, 1)
    assert c.post(f"/api/builds/{a}/favorite", json={"favorite": True}).json()["favorite"] is True      # the oldest is starred
    e = photo_build(c)                                                                                     # 4th build: the oldest UN-starred (b) rolls off
    assert _exists(a) and not _exists(b) and _exists(d) and _exists(e)
    assert c.post(f"/api/builds/{d}/favorite", json={"favorite": True}).status_code == 200
    assert c.post(f"/api/builds/{e}/favorite", json={"favorite": True}).status_code == 200
    r = b1.gen(c)                                                                                          # all three starred: refuse, delete nothing
    assert r.status_code == 409 and r.json()["all_favorites"] is True and "Un-star or delete one" in r.json()["message"]
    assert _exists(a) and _exists(d) and _exists(e)
    assert c.post("/api/builds/delete-oldest").json()["deleted"] is None                                 # the quick 'delete oldest' skips starred too
    c.delete(f"/api/builds/{a}"); assert not _exists(a)                                                   # the owner can delete a starred build
    assert b1.gen(c).status_code == 200                                                                    # and there is room again


def test_only_the_owner_can_star_and_the_flag_shows_in_the_list():
    c = client(ADULT); bid = photo_build(c)
    assert client(ADULT).post(f"/api/builds/{bid}/favorite", json={"favorite": True}).status_code in (403, 404)
    c.post(f"/api/builds/{bid}/favorite", json={"favorite": True})
    row = [x for x in c.get("/api/builds").json()["builds"] if x["id"] == bid][0]
    assert row["favorite"] is True and row["expires"] is None


def test_age_rules_30_days_ordinary_saved_and_starred_exempt():
    # the policy function, exactly: ordinary = 30 days, saved/starred exempt
    assert retention.keep_days({}) == 30.0
    assert retention.keep_days({"saved": True}) is None
    assert retention.keep_days({"favorite": True}) is None
    assert retention.keep_days({"saved": True, "favorite": True}) is None
    # enforcement, with margins either side of the 30-day line
    c = client(ADULT); plain, shared, starred, old_star, old_saved = (photo_build(c) for _ in range(5))
    r = c.post("/api/showcase", json={"build_id": shared, "title": "Saved one", "accept_guidelines": True, "nsfw": False, "visibility": "private"}); assert r.status_code == 200, r.text
    assert store.get(shared)["saved"] is True
    c.post(f"/api/builds/{starred}/favorite", json={"favorite": True}); c.post(f"/api/builds/{old_star}/favorite", json={"favorite": True})
    c.post("/api/showcase", json={"build_id": old_saved, "title": "Old saved", "accept_guidelines": True, "nsfw": False, "visibility": "private"})
    _age(old_saved, 400)
    for bid in (plain, shared, starred): _age(bid, 29)
    _age(old_star, 400)
    out = retention.purge_expired()
    # a day short of 30: nothing expires; saved/starred never do
    assert _exists(plain) and _exists(shared) and _exists(starred) and _exists(old_star) and _exists(old_saved)
    assert out["expired"] == 0
    _age(plain, 31); retention.purge_expired()
    assert not _exists(plain)                     # past the 30-day line: ordinary build gone
    assert _exists(shared) and _exists(starred) and _exists(old_star) and _exists(old_saved)
    assert [x for x in c.get("/api/builds").json()["builds"] if x["id"] == starred][0]["expires"] is None
    assert [x for x in c.get("/api/builds").json()["builds"] if x["id"] == old_saved][0]["expires"] is None


def test_unfinished_folders_go_after_a_day_and_logs_carry_counts_not_names(caplog):
    junk = store.root / "abandoned1"; junk.mkdir(); (junk / "x.bin").write_bytes(b"1")
    fresh = store.root / "fresh1"; fresh.mkdir()
    old = time.time() - 2 * 86400; os.utime(junk, (old, old))
    c = client(ADULT); bid = photo_build(c); _age(bid, 31)      # past the 30-day ordinary-build line
    with caplog.at_level(logging.INFO, logger="zeim.cleanup"):
        retention.purge_expired()
    assert not junk.exists() and fresh.exists() and not _exists(bid)
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "removed" in text and bid not in text and "abandoned1" not in text and "Ada" not in text
    fresh.rmdir()


def test_cleanup_only_touches_build_folders_and_refuses_the_library_static_and_code(tmp_path):
    for name in ("library", "static", "app", "tests"):
        with pytest.raises(PermissionError):
            retention.purge_expired(BuildStore(root=config.ROOT / name))
    with pytest.raises(PermissionError):
        retention.purge_expired(BuildStore(root=config.ROOT))
    with pytest.raises(PermissionError):
        retention.purge_expired(BuildStore(root=config.ROOT / "library" / "originals"))
    # inside a legitimate build folder: a sibling 'library', plain files and a symlink are left alone
    root = tmp_path / "out"; root.mkdir(); lib = tmp_path / "library"; (lib / "originals").mkdir(parents=True); (lib / "originals" / "m.stl").write_bytes(b"x")
    (root / "notes.txt").write_text("x"); (root / "link1").symlink_to(lib, target_is_directory=True)
    (root / "not-a-build-name").mkdir(); old = time.time() - 9 * 86400; os.utime(root / "not-a-build-name", (old, old))
    bs = BuildStore(root=root); retention.purge_expired(bs, now=time.time() + 90 * 86400)
    assert (lib / "originals" / "m.stl").exists() and (root / "notes.txt").exists() and (root / "link1").is_symlink() and (root / "not-a-build-name").exists()


def test_a_starred_build_survives_cleanup_and_a_disk_low_sweep_and_heavy_builds_are_refused_instead(monkeypatch):
    c = client(ADULT); fav, plain = photo_build(c), photo_build(c)
    c.post(f"/api/builds/{fav}/favorite", json={"favorite": True}); _age(fav, 400); _age(plain, 1)
    def free(root=None):
        return (50 if _exists(plain) else 10) * 1024 ** 2          # always low: deleting the unstarred build does not free enough
    monkeypatch.setattr(retention, "free_bytes", free)
    monkeypatch.setattr(config, "DISK_MIN_FREE_MB", 500); monkeypatch.setattr(config, "DISK_TARGET_FREE_MB", 1000)
    r = b1.gen(c)
    assert r.status_code == 507 and "almost full" in r.json()["detail"] and "Starred builds are never removed" in r.json()["detail"]
    assert _exists(fav) and not _exists(plain)                                       # the sweep took the unstarred one only
    assert c.post(f"/api/edit/new", files={"file": ("b.stl", b1.box_stl(), "application/octet-stream")}).status_code == 507
    out = retention.sweep_for_space(); assert _exists(fav) and out["swept"] == 0
    assert retention.purge_expired()["kept_starred"] >= 1 and _exists(fav)
    monkeypatch.setattr(retention, "free_bytes", lambda root=None: 10 ** 12)
    assert b1.gen(c).status_code == 200                                              # disk fine again: builds work


def test_a_sweep_frees_room_with_unstarred_builds_and_the_build_then_goes_through(monkeypatch):
    c = client(ADULT); fav, plain = photo_build(c), photo_build(c)
    c.post(f"/api/builds/{fav}/favorite", json={"favorite": True}); _age(plain, 1)
    monkeypatch.setattr(retention, "free_bytes", lambda root=None: (600 if not _exists(plain) else 100) * 1024 ** 2)
    monkeypatch.setattr(config, "DISK_MIN_FREE_MB", 500); monkeypatch.setattr(config, "DISK_TARGET_FREE_MB", 550)
    assert b1.gen(c).status_code == 200 and not _exists(plain) and _exists(fav)


def test_delete_my_stuff_and_delete_everything_remove_starred_builds_and_their_files():
    a = client(ADULT); b2 = photo_build(a); a.post(f"/api/builds/{b2}/favorite", json={"favorite": True})
    b3 = photo_build(a); a.post("/api/showcase", json={"build_id": b3, "title": "Shared", "accept_guidelines": True, "nsfw": False, "visibility": "private"})
    out = a.delete("/api/me/builds").json()
    assert out["ok"] and out["builds"] == 2 and out["shared"] == 1
    assert not store.dir(b2).exists() and not store.dir(b3).exists() and a.get("/api/builds").json()["builds"] == []


def test_defaults_are_documented_and_configurable():
    assert (config.MAX_BUILDS, config.KEEP_UNSAVED_DAYS, config.KEEP_SAVED_DAYS) == (20, 30, 30)
    assert "PHOTO3D_KEEP_UNSAVED_DAYS" in open(config.ROOT / "app" / "config.py").read()


def test_capacity_of_only_starred_and_saved_builds_is_full_not_evicted(monkeypatch):
    """Starred/saved builds are never rolled off for capacity: a full history of only-exempt
    builds raises HistoryFull instead of deleting someone's saved work."""
    monkeypatch.setattr(config, "UPLOADS_PER_HOUR", 0)     # the gate's hourly limit is not under test here
    c = client(ADULT)
    from app.services.history import HistoryFull
    for i in range(config.MAX_BUILDS):
        bid = photo_build(c)
        if i < 2:
            c.post(f"/api/builds/{bid}/favorite", json={"favorite": True})
        else:
            c.post("/api/showcase", json={"build_id": bid, "title": f"S{i}", "accept_guidelines": True,
                                          "nsfw": False, "visibility": "private"})
    before = {m["id"] for m in c.get("/api/builds").json()["builds"]}
    assert len(before) == config.MAX_BUILDS
    r = c.post("/api/generate", files={"file": ("photo.png", _png_bytes(), "image/png")}, data={"mode": "relief"})
    assert r.status_code == 409 and r.json()["code"] == "history_full"   # full: refuse, never evict
    assert {m["id"] for m in c.get("/api/builds").json()["builds"]} == before


def test_disk_sweep_skips_saved_builds_too():
    """The disk-pressure sweep removes oldest UNPROTECTED builds — saved ones are exempt."""
    c = client(ADULT)
    plain = photo_build(c)
    saved = photo_build(c)
    c.post("/api/showcase", json={"build_id": saved, "title": "Kept", "accept_guidelines": True,
                                 "nsfw": False, "visibility": "private"})
    old = time.time() - 40 * 86400
    for bid in (plain, saved):
        m = store.get(bid); m["created"] = datetime.fromtimestamp(old, timezone.utc).isoformat(); store.save(m)
    out = retention.sweep_for_space(now=time.time() + 60) if False else None
    # direct call with a target that forces sweeping
    out = retention.sweep_for_space()
    assert not _exists(plain) and _exists(saved)


def _png_bytes():
    import io
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (50, 40), (1, 2, 3)).save(b, "PNG")
    return b.getvalue()
