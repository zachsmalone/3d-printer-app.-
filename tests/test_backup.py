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
