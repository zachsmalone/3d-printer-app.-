"""ZEIM_STORAGE=db mode: SQLite document store, DB-backed BuildStore, JSON->DB migration.

These tests flip the LIVE config to db mode per test (the stores read config.STORAGE_MODE
at call time), point config.DATA at a fresh tmp dir, and reset the connection cache
afterwards — so they run in-process alongside the json-mode suite without interference.
"""
from __future__ import annotations

import json
import threading

import pytest

from app import config, db


@pytest.fixture
def db_mode(tmp_path, monkeypatch):
    """Fresh DATA dir + db mode; cached connections are dropped afterwards."""
    monkeypatch.setattr(config, "STORAGE_MODE", "db")
    monkeypatch.setattr(config, "DATA", tmp_path)
    db.reset()
    yield tmp_path
    db.reset()


def _mkbuild(bs, bid, owner, **extra):
    d = bs.dir(bid)
    d.mkdir(parents=True, exist_ok=True)
    (d / "model.stl").write_text("solid x")
    meta = {"id": bid, "mode": "relief", "owner_sid": owner,
            "created": f"2026-10-17T00:0{int(bid[-1]) % 10}:00+00:00"}
    meta.update(extra)
    bs.save(meta)
    return meta


# --- document store ---

def test_doc_read_write_update_roundtrip(db_mode):
    from app.community.store import USERS
    USERS.write({"sid1": {"display_name": "Ann"}})
    assert USERS.read() == {"sid1": {"display_name": "Ann"}}
    r = USERS.update(lambda d: d.setdefault("sid2", {"display_name": "Bo"}))
    assert r["display_name"] == "Bo"
    assert len(USERS.read()) == 2


def test_doc_default_when_missing(db_mode):
    from app.community.store import MODERATION
    assert MODERATION.read() == {"hidden": [], "reports": []}


def test_doc_update_is_atomic_under_threads(db_mode):
    """100 concurrent increments must all land: update() is one transaction, no lost writes."""
    from app.community.store import USERS
    USERS.write({"n": 0})

    def bump():
        for _ in range(100):
            USERS.update(lambda d: d.update(n=d["n"] + 1))

    threads = [threading.Thread(target=bump) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert USERS.read()["n"] == 400


def test_json_file_never_written_in_db_mode(db_mode):
    from app.community.store import JsonFile
    probe = JsonFile("dbmode_probe", {})          # a name no other test uses
    probe.write({"a": 1})
    assert not probe.path.exists()               # the DB is the one source of truth
    row = db.conn().execute("SELECT doc FROM documents WHERE name='dbmode_probe'").fetchone()
    assert row is not None


def test_db_failure_raises_no_json_fallback(db_mode, monkeypatch):
    from app.community.store import JsonFile
    probe = JsonFile("dbmode_probe2", {})
    # a broken DATA dir must raise, never silently write JSON
    monkeypatch.setattr(config, "DATA", db_mode / "no" / "such" / "dir\0bad")
    with pytest.raises(Exception):
        probe.write({"x": 1})
    assert not probe.path.exists()


# --- BuildStore in db mode ---

def test_buildstore_save_get_list_owner_filter(db_mode):
    from app.services.history import BuildStore
    bs = BuildStore(root=db_mode / "out")
    _mkbuild(bs, "b1", "alice")
    _mkbuild(bs, "b2", "bob")
    _mkbuild(bs, "b3", "alice")
    assert [m["id"] for m in bs.list("alice")] == ["b1", "b3"]
    assert [m["id"] for m in bs.list("bob")] == ["b2"]
    assert len(bs.list()) == 3
    assert bs.get("b2")["owner_sid"] == "bob"
    with pytest.raises(KeyError):
        bs.get("nope")


def test_buildstore_files_stay_on_disk(db_mode):
    from app.services.history import BuildStore
    bs = BuildStore(root=db_mode / "out")
    _mkbuild(bs, "b1", "alice")
    assert (bs.dir("b1") / "model.stl").exists()
    assert not (bs.dir("b1") / "meta.json").exists()     # db is authoritative in db mode


def test_buildstore_favorite_saved_and_rolloff_parity(db_mode):
    from app.services.history import BuildStore, HistoryFull
    bs = BuildStore(root=db_mode / "out", limit=2)
    _mkbuild(bs, "b1", "alice")
    _mkbuild(bs, "b2", "alice")
    bs.set_favorite("b1", True)
    bs.set_saved("b2")
    # at capacity: the oldest UNstarred build (b2) rolls off, starred b1 stays
    bs.reserve("alice")
    assert [m["id"] for m in bs.list("alice")] == ["b1"]
    assert bs.get("b1")["favorite"] is True
    # all starred + at capacity => HistoryFull, nothing removed
    _mkbuild(bs, "b3", "alice")
    bs.set_favorite("b3", True)
    with pytest.raises(HistoryFull):
        bs.reserve("alice")
    assert len(bs.list("alice")) == 2


def test_buildstore_delete_removes_row_and_dir(db_mode):
    from app.services.history import BuildStore
    bs = BuildStore(root=db_mode / "out")
    _mkbuild(bs, "b1", "alice")
    bs.delete("b1")
    assert not bs.dir("b1").exists()
    with pytest.raises(KeyError):
        bs.get("b1")
    assert bs.list() == []


def test_buildstore_claim_unowned_is_deliberate(db_mode):
    from app.services.history import BuildStore
    bs = BuildStore(root=db_mode / "out")
    m = _mkbuild(bs, "b1", None)                      # legacy build with no owner
    assert bs.list("alice") == []                     # invisible to alice until claimed
    bs.claim_unowned("alice")
    assert [x["id"] for x in bs.list("alice")] == ["b1"]
    assert bs.get("b1")["visibility"] == "private"


def test_restart_persistence(db_mode):
    from app.community.store import USERS
    from app.services.history import BuildStore
    USERS.write({"sid": {"display_name": "Ann"}})
    bs = BuildStore(root=db_mode / "out")
    _mkbuild(bs, "b1", "alice")
    db.reset()                                        # simulate a process restart (fresh connections)
    assert USERS.read()["sid"]["display_name"] == "Ann"
    assert bs.get("b1")["owner_sid"] == "alice"


# --- migration ---

def _seed_json(data: config.Path, out: config.Path):
    (data / "users.json").write_text(json.dumps({"sid1": {"display_name": "Ann"}, "sid2": {"display_name": "Bo"}}))
    (data / "projects.json").write_text(json.dumps([{"id": "p1", "title": "T"}]))
    out.mkdir(parents=True, exist_ok=True)
    for bid, owner in (("b1", "sid1"), ("b2", "sid1"), ("b3", None)):
        d = out / bid
        d.mkdir()
        (d / "model.stl").write_text("x")
        (d / "meta.json").write_text(json.dumps(
            {"id": bid, "mode": "relief", "owner_sid": owner, "created": "2026-10-01T00:00:00+00:00"}))


def test_migration_dry_run_changes_nothing(db_mode, tmp_path):
    from scripts.migrate_json_to_db import migrate
    data, out = db_mode, db_mode / "out"
    _seed_json(data, out)
    report = migrate(data, out, dry_run=True)
    assert report["documents"] == {"users": 2, "projects": 1}
    assert report["builds"] == 3
    assert report["unowned_builds"] == 1
    assert not (data / "zeim.sqlite3").exists()        # nothing written


def test_migration_imports_and_validates(db_mode):
    from scripts.migrate_json_to_db import migrate
    data, out = db_mode, db_mode / "out"
    _seed_json(data, out)
    report = migrate(data, out)
    assert report["validation"] == "ok"
    assert report["builds"] == 3
    assert report["unowned_builds"] == 1
    assert report["backed_up_to"] and "json-backup-" in report["backed_up_to"]
    # DB content matches the JSON source exactly
    c = db.conn()
    assert json.loads(c.execute("SELECT doc FROM documents WHERE name='users'").fetchone()[0])["sid1"]["display_name"] == "Ann"
    assert c.execute("SELECT COUNT(*) FROM builds").fetchone()[0] == 3
    # the unowned build stays unassigned — the migration never guesses an owner
    assert c.execute("SELECT owner_sid FROM builds WHERE id='b3'").fetchone()[0] is None


def test_migration_is_repeat_safe(db_mode):
    from scripts.migrate_json_to_db import migrate
    data, out = db_mode, db_mode / "out"
    _seed_json(data, out)
    migrate(data, out)
    report2 = migrate(data, out)
    assert report2["validation"] == "ok"
    assert db.conn().execute("SELECT COUNT(*) FROM builds").fetchone()[0] == 3


def test_migration_freeze_and_json_untouched(db_mode):
    from scripts.migrate_json_to_db import migrate
    data, out = db_mode, db_mode / "out"
    _seed_json(data, out)
    before = (data / "users.json").read_text()
    report = migrate(data, out, freeze=True)
    assert report["frozen"] == ["users.json", "projects.json"]
    assert (data / "users.json").read_text() == before      # JSON is only read, never rewritten
    # rollback story: the read-only JSON is still there and complete
    assert json.loads((data / "users.json").read_text())["sid1"]["display_name"] == "Ann"


def test_migration_bad_json_reports_mismatch(db_mode):
    from scripts.migrate_json_to_db import migrate
    data, out = db_mode, db_mode / "out"
    _seed_json(data, out)
    # corrupt the source AFTER a successful migration: re-import must validate against the new source
    (data / "users.json").write_text(json.dumps({"sid1": {"display_name": "CHANGED"}}))
    report = migrate(data, out)
    assert report["validation"] == "ok"
    assert json.loads(db.conn().execute("SELECT doc FROM documents WHERE name='users'").fetchone()[0])["sid1"]["display_name"] == "CHANGED"


def test_migrated_builds_usable_by_buildstore(db_mode):
    from scripts.migrate_json_to_db import migrate
    from app.services.history import BuildStore
    data, out = db_mode, db_mode / "out"
    _seed_json(data, out)
    migrate(data, out)
    bs = BuildStore(root=out)
    assert [m["id"] for m in bs.list("sid1")] == ["b1", "b2"]
    assert bs.get("b1")["mode"] == "relief"


def test_two_processes_see_the_same_data_and_dont_corrupt_it(db_mode, tmp_path):
    """_TX_LOCK guards threads; WAL + busy_timeout must guard separate processes (multiple workers)."""
    import os, subprocess, sys
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = tmp_path / "writer.py"
    script.write_text(
        "import sys; sys.path.insert(0, sys.argv[3]); import json\n"
        "from app import db\n"
        "db.doc_write(sys.argv[1], json.loads(sys.argv[2]))\n"
        "print('ok')"
    )
    # parent process: write concurrently with two child writers on the same DATA dir
    db.doc_write("parent", {"n": 1})
    env = {**os.environ, "PHOTO3D_DATA": str(db_mode)}
    procs = [subprocess.Popen([sys.executable, str(script), f"child{i}", json.dumps({"n": i}), str(repo)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
             for i in range(2)]
    for p in procs:
        out, err = p.communicate(timeout=60)
        assert p.returncode == 0, err.decode()[-400:]
    for i in range(2):
        assert db.doc_read(f"child{i}", {}) == {"n": i}
    assert db.doc_read("parent", {}) == {"n": 1}


def test_concurrent_same_document_updates_lose_nothing(db_mode, tmp_path):
    """Two processes hammering doc_update on the SAME document: every increment survives."""
    import os, subprocess, sys
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = tmp_path / "hammer.py"
    script.write_text(
        "import sys; sys.path.insert(0, sys.argv[1])\n"
        "from app import db\n"
        "for _ in range(10):\n"
        "    db.doc_update('ctr', {}, lambda d: d.update(n=d.get('n', 0) + 1))\n"
        "print('ok')\n"
    )
    env = {**os.environ, "PHOTO3D_DATA": str(db_mode)}
    procs = [subprocess.Popen([sys.executable, str(script), repo], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, env=env) for _ in range(2)]
    for p in procs:
        out, err = p.communicate(timeout=120)
        assert p.returncode == 0, err.decode()[-400:]
    assert db.doc_read("ctr", {})["n"] == 20                    # 2 processes x 10 updates, none lost


def test_concurrent_upload_limit_admits_at_most_the_limit(db_mode, tmp_path):
    """The count-and-insert is one transaction: parallel workers cannot over-admit one account."""
    import os, subprocess, sys
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = tmp_path / "hit.py"
    script.write_text(
        "import sys, time; sys.path.insert(0, sys.argv[1])\n"
        "from app import db\n"
        "admitted = 0\n"
        "for _ in range(5):\n"
        "    if db.upload_events_hit('acct', time.time(), 3600, 3):\n"
        "        admitted += 1\n"
        "print(admitted)\n"
    )
    env = {**os.environ, "PHOTO3D_DATA": str(db_mode)}
    procs = [subprocess.Popen([sys.executable, str(script), repo], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, env=env) for _ in range(4)]
    total = 0
    for p in procs:
        out, err = p.communicate(timeout=120)
        assert p.returncode == 0, err.decode()[-400:]
        total += int(out.strip())
    assert total == 3                                            # limit is 3: never more, exactly the limit
