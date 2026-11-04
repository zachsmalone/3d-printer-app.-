import sqlite3, tarfile
from datetime import datetime
from app.services import offpeak


def test_next_run_is_tonight_or_tomorrow_in_chicago():
    now = datetime(2026, 11, 3, 22, 0, tzinfo=offpeak.TZ)
    assert offpeak.next_run(now, 3, 0) == datetime(2026, 11, 4, 3, 0, tzinfo=offpeak.TZ)
    early = datetime(2026, 11, 4, 1, 0, tzinfo=offpeak.TZ)
    assert offpeak.next_run(early, 3, 30).day == 4


def test_backup_archives_data_skips_backups_and_keeps_three(tmp_path, monkeypatch):
    monkeypatch.setattr(offpeak.config, "DATA", tmp_path)
    (tmp_path / "builds").mkdir(); (tmp_path / "builds" / "a.json").write_text("{}")
    db = sqlite3.connect(tmp_path / "auth.sqlite3"); db.execute("create table t(x)"); db.execute("insert into t values(1)"); db.commit(); db.close()
    for d in range(1, 6):
        f = offpeak.run_backup(datetime(2026, 11, d, 3, 30, tzinfo=offpeak.TZ))
    kept = sorted(p.name for p in offpeak.backup_dir().glob("data-*.tgz"))
    assert kept == ["data-20261103-0330.tgz", "data-20261104-0330.tgz", "data-20261105-0330.tgz"]
    names = tarfile.open(f).getnames()
    assert "builds/a.json" in names and "auth.sqlite3" in names and not any(n.startswith("_backups") for n in names)
    assert oct(f.stat().st_mode & 0o777) == "0o600"


def test_main_uses_offpeak_scheduler():
    src = open("app/main.py").read()
    assert "offpeak.start_background()" in src and "retention.start_background()" not in src
