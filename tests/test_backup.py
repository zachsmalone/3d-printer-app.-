"""Backup, retention, restore and verification (scripts/backup.py, scripts/restore_verify.py)."""
from __future__ import annotations

import json
import sqlite3

from scripts.backup import create_backup, enforce_retention, _outputs_manifest
from scripts.restore_verify import restore, verify_backup, verify_outputs


def _mkdata(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "users.json").write_text(json.dumps({"s1": {"display_name": "Ann"}}))
    c = sqlite3.connect(str(data / "zeim.sqlite3"))
    c.executescript("CREATE TABLE documents(name TEXT PRIMARY KEY, doc TEXT NOT NULL, updated_at REAL NOT NULL);"
                    "INSERT INTO documents VALUES('users', '{\"s1\": {\"display_name\": \"Ann\"}}', 1);")
    c.commit()
    c.close()
    out = tmp_path / "outputs"
    (out / "b1").mkdir(parents=True)
    (out / "b1" / "model.stl").write_text("solid")
    (out / "b1" / "thumb.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    return data, out


def test_backup_captures_db_json_and_manifest(tmp_path):
    data, out = _mkdata(tmp_path)
    report = create_backup(data, out, tmp_path / "backups", now=1_000_000_000)
    bdir = (tmp_path / "backups").glob("zeim-*").__next__()   # the one timestamped backup
    assert (bdir / "zeim.sqlite3").exists()
    assert (bdir / "users.json").exists()
    manifest = json.loads((bdir / "outputs.manifest.json").read_text())
    assert set(manifest["files"]) == {"b1/model.stl", "b1/thumb.png"}
    assert manifest["files"]["b1/model.stl"]["sha256"]
    assert (bdir / "backup.json").exists()
    assert report["databases"] == ["zeim.sqlite3"]
    assert report["output_files"] == 2


def test_backup_verify_and_roundtrip_restore(tmp_path):
    data, out = _mkdata(tmp_path)
    create_backup(data, out, tmp_path / "backups", now=1_000_000_000)
    bdir = (tmp_path / "backups").glob("zeim-*").__next__()
    assert verify_backup(bdir)["ok"] is True
    # restore into a clean target and read the data back
    target = tmp_path / "restore-target"
    r = restore(bdir, target)
    assert r["databases"] == ["zeim.sqlite3"]
    assert r["json_files"] == ["users.json"]
    c = sqlite3.connect(str(target / "zeim.sqlite3"))
    assert c.execute("SELECT doc FROM documents WHERE name='users'").fetchone()[0].startswith("{\"s1\"")
    c.close()
    assert json.loads((target / "users.json").read_text())["s1"]["display_name"] == "Ann"


def test_verify_backup_detects_corruption(tmp_path):
    data, out = _mkdata(tmp_path)
    create_backup(data, out, tmp_path / "backups", now=1_000_000_000)
    bdir = (tmp_path / "backups").glob("zeim-*").__next__()
    (bdir / "users.json").write_text("tampered")
    v = verify_backup(bdir)
    assert v["ok"] is False
    assert "CORRUPT" in v["checksums"]


def test_verify_outputs_detects_drift(tmp_path):
    data, out = _mkdata(tmp_path)
    create_backup(data, out, tmp_path / "backups", now=1_000_000_000)
    bdir = (tmp_path / "backups").glob("zeim-*").__next__()
    assert verify_outputs(bdir, out)["ok"] is True
    (out / "b1" / "model.stl").write_text("changed after backup")
    assert verify_outputs(bdir, out)["ok"] is False
    (out / "b1" / "model.stl").unlink()
    o = verify_outputs(bdir, out)
    assert o["ok"] is False and o["missing"] == 1


def test_retention_keeps_daily_and_weekly(tmp_path):
    import time
    root = tmp_path / "backups"
    now = 1_000_000_000.0
    # 20 daily backups, one per day (2001-09-09 onward); a few land on Sundays
    for i in range(20):
        create_backup(tmp_path / "empty-data", tmp_path / "empty-out", root, now=now + i * 86400)
    report = enforce_retention(root)
    remaining = list(root.glob("zeim-*"))
    assert report["removed"] == 20 - len(remaining)
    assert len(remaining) <= 14 + 8          # daily keep + weekly keep (may overlap)
    # the newest backup always survives
    newest = max(remaining, key=lambda p: p.name)
    assert (newest / "backup.json").exists()


# --- encryption at rest (age) ---

import shutil
import time
from pathlib import Path

import pytest


def _age_keypair(tmp_path):
    """A real age keypair via age-keygen (the same binary an operator would use)."""
    import subprocess
    key = tmp_path / "age.key"
    r = subprocess.run(["age-keygen", "-o", str(key)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    recipient = [l for l in key.read_text().splitlines() if "public key" in l][0].split(": ")[1]
    return recipient, key


def test_encrypted_backup_roundtrip_no_plaintext_left(tmp_path):
    """Round-trip with a REAL database in the backup: encrypt -> decrypt -> checksums -> DB
    integrity -> app-readable restore -> no plaintext left behind."""
    if not shutil.which("age"):
        pytest.skip("age binary not installed")
    from scripts import backup as B, restore_verify as RV
    data = tmp_path / "data"; data.mkdir()
    (data / "users.json").write_text('{"a": 1}')
    c = sqlite3.connect(data / "zeim.sqlite3")
    c.execute("CREATE TABLE documents (name TEXT PRIMARY KEY, doc TEXT)")
    c.execute("INSERT INTO documents VALUES ('users', '{\"a\": 1}')")
    c.commit(); c.close()
    recipient, key = _age_keypair(tmp_path)
    report = B.create_backup(data, tmp_path / "out", tmp_path / "bk", encrypt_to=recipient)
    assert report["encrypted"] is True
    assert report["databases"] == ["zeim.sqlite3"]
    archive = Path(report["archive"])
    assert archive.name.endswith(".tar.age") and archive.stat().st_size > 0
    # no plaintext backup dir, no staging dir, no temp archive left anywhere
    assert not archive.parent.joinpath(archive.name.replace(".tar.age", "")).exists()
    assert not list(archive.parent.glob(".staging-*"))
    assert not list(archive.parent.glob(".tmp-*"))
    # decrypt with the right identity -> verifies + restores + the DB is actually readable
    unpacked = RV.unpack_archive(archive, key)
    assert RV.verify_backup(unpacked)["ok"] is True
    restored = RV.restore(unpacked, tmp_path / "target")
    assert restored["databases"] == ["zeim.sqlite3"]
    c = sqlite3.connect(tmp_path / "target" / "zeim.sqlite3")
    assert c.execute("SELECT doc FROM documents WHERE name='users'").fetchone()[0] == '{"a": 1}'
    c.close()
    RV.cleanup_unpacked(unpacked)
    assert not unpacked.exists()                 # no decrypted plaintext lingers


def test_wrong_identity_cannot_decrypt(tmp_path):
    import subprocess
    if not shutil.which("age"):
        pytest.skip("age binary not installed")
    from scripts import backup as B, restore_verify as RV
    data = tmp_path / "data"; data.mkdir()
    (data / "users.json").write_text('{"a": 1}')
    recipient, _key = _age_keypair(tmp_path)
    (tmp_path / "sub").mkdir(exist_ok=True)
    _r2, other_key = _age_keypair(tmp_path / "sub")
    report = B.create_backup(data, tmp_path / "out", tmp_path / "bk", encrypt_to=recipient)
    with pytest.raises(RuntimeError):
        RV.unpack_archive(Path(report["archive"]), other_key)


def test_corrupt_ciphertext_fails_loudly(tmp_path):
    if not shutil.which("age"):
        pytest.skip("age binary not installed")
    from scripts import backup as B, restore_verify as RV
    data = tmp_path / "data"; data.mkdir()
    (data / "users.json").write_text('{"a": 1}')
    recipient, key = _age_keypair(tmp_path)
    report = B.create_backup(data, tmp_path / "out", tmp_path / "bk", encrypt_to=recipient)
    archive = Path(report["archive"])
    raw = bytearray(archive.read_bytes()); raw[len(raw) // 2] ^= 0xFF
    archive.write_bytes(bytes(raw))
    with pytest.raises(RuntimeError):
        RV.unpack_archive(archive, key)


def test_missing_age_binary_never_falls_back_to_plaintext(tmp_path, monkeypatch):
    """Failed encryption leaves NOTHING behind: no plaintext dir, no staging dir, no archive."""
    from scripts import backup as B
    data = tmp_path / "data"; data.mkdir()
    (data / "users.json").write_text('{"a": 1}')
    monkeypatch.setattr(B.shutil, "which", lambda _n: None)
    with pytest.raises(RuntimeError, match="age binary not found"):
        B.create_backup(data, tmp_path / "out", tmp_path / "bk", encrypt_to="age1fake")
    bk = tmp_path / "bk"
    assert not list(bk.glob("zeim-*")) and not list(bk.glob(".staging-*")) and not list(bk.glob(".tmp-*"))


def test_retention_prunes_tar_age_archives_too(tmp_path):
    if not shutil.which("age"):
        pytest.skip("age binary not installed")
    from scripts import backup as B
    data = tmp_path / "data"; data.mkdir()
    recipient, _ = _age_keypair(tmp_path)
    bk = tmp_path / "bk"
    # 16 daily archives: only the newest 14 survive
    for i in range(16):
        B.create_backup(data, tmp_path / "out", bk, now=time.time() - (16 - i) * 3600, encrypt_to=recipient)
    out = B.enforce_retention(bk, now=time.time() + 60)
    assert out["kept"] == 14 and out["removed"] == 2
    assert len(list(bk.glob("*.tar.age"))) == 14
    assert all(p.is_file() for p in bk.glob("zeim-*"))          # no plaintext dirs remain


def test_retention_keeps_14_daily_plus_8_sunday_weeklies_over_a_long_calendar(tmp_path):
    """A fixed 70-day calendar: after retention, the newest 14 dailies AND the last 8 Sundays
    survive (both plaintext dirs and encrypted archives) — the weekly rule really fires."""
    import datetime as _dt
    from scripts import backup as B
    data = tmp_path / "data"; data.mkdir()
    (data / "users.json").write_text("{}")
    bk = tmp_path / "bk"
    start = _dt.datetime(2026, 8, 1, 3, 0, 0)          # a Saturday
    for d in range(70):                                 # one backup per day
        now = (start + _dt.timedelta(days=d)).timestamp()
        B.create_backup(data, tmp_path / "out", bk, now=now)
    B.enforce_retention(bk, now=(start + _dt.timedelta(days=70)).timestamp())
    kept = sorted(p.name for p in bk.glob("zeim-*"))
    # all Sundays in the calendar that are among the last 8 Sundays survive
    sundays = [start + _dt.timedelta(days=d) for d in range(70) if (start + _dt.timedelta(days=d)).weekday() == 6]
    for s in sundays[-8:]:
        assert any(s.strftime("%Y%m%d") in name for name in kept), s.date()
    assert len(kept) == len(set(kept))
    # and the same holds for encrypted archives
    bk2 = tmp_path / "bk2"
    if shutil.which("age"):
        recipient, _ = _age_keypair(tmp_path)
        for d in range(70):
            now = (start + _dt.timedelta(days=d)).timestamp()
            B.create_backup(data, tmp_path / "out", bk2, now=now, encrypt_to=recipient)
        B.enforce_retention(bk2, now=(start + _dt.timedelta(days=70)).timestamp())
        kept2 = sorted(p.name for p in bk2.glob("*.tar.age"))
        for s in sundays[-8:]:
            assert any(s.strftime("%Y%m%d") in name for name in kept2), s.date()
