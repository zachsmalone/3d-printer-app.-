"""RET5: restore-drill.sh restores the newest set into scratch, checks it against live, never touches live."""
import os
import sqlite3
import subprocess
from pathlib import Path

DRILL = Path(__file__).resolve().parents[1] / "reports" / "deploy" / "restore-drill.sh"


def _live(tmp):
    data = tmp / "srv/data"; data.mkdir(parents=True); (tmp / "srv/outputs/b1").mkdir(parents=True)
    (data / "users.json").write_text('{"a": 1}')
    c = sqlite3.connect(data / "zeim.sqlite3"); c.execute("create table t(x)"); c.execute("insert into t values(1)"); c.commit(); c.close()
    (tmp / "srv/outputs/b1/m.stl").write_text("solid")
    return data


def _run(tmp, backups):
    env = dict(os.environ, ZEIM_HOST_DIR=str(tmp / "srv"), BACKUP_DIR=str(backups), DRILL_LOG=str(tmp / "drill.log"))
    return subprocess.run(["bash", str(DRILL)], env=env, capture_output=True, text=True)


def test_drill_passes_without_existing_sets_and_leaves_live_alone(tmp_path):
    data = _live(tmp_path)
    before = sorted((p.name, p.stat().st_mtime) for p in data.iterdir())
    r = _run(tmp_path, tmp_path / "none")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASS" in r.stdout and "(fresh)" in r.stdout
    assert sorted((p.name, p.stat().st_mtime) for p in data.iterdir()) == before
    assert "PASS" in (tmp_path / "drill.log").read_text()


def test_drill_fails_on_corrupt_set(tmp_path):
    _live(tmp_path)
    b = tmp_path / "bk"
    env = dict(os.environ, ZEIM_HOST_DIR=str(tmp_path / "srv"), BACKUP_DIR=str(b))
    subprocess.run(["bash", str(DRILL.parent / "backup.sh")], env=env, check=True, capture_output=True)
    s = next(b.glob("*/zeim-*")); f = next(s.glob("data.tar.gz*"))
    f.write_bytes(f.read_bytes()[:-10] + b"corrupted!")
    r = _run(tmp_path, b)
    assert r.returncode != 0 and "FAIL" in r.stdout
