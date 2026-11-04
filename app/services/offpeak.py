"""PERF10: heavy upkeep runs once a night at a quiet hour, in one low-priority background thread.

* 03:00 America/Chicago - retention clean-up (expired build files; starred builds are never touched).
* 03:30 America/Chicago - nightly backup of the data folder into DATA/_backups (last KEEP copies kept).

Account deletions stay hourly (services in account_delete.py): they are user requests and tiny.
Set ZEIM_NIGHTLY_BACKUP=0 to turn the backup off (e.g. on a laptop)."""
from __future__ import annotations

import logging, os, shutil, sqlite3, tarfile, threading, time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import config

log = logging.getLogger("zeim.offpeak")
TZ = ZoneInfo("America/Chicago")
KEEP = int(os.environ.get("ZEIM_BACKUP_KEEP", "3"))
JOBS = [(3, 0, "retention"), (3, 30, "backup")]
SKIP_DIRS = {"_backups", "tmp", "cache"}


def next_run(now: datetime, hour: int, minute: int) -> datetime:
    t = now.astimezone(TZ).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return t if t > now.astimezone(TZ) else t + timedelta(days=1)


def backup_dir() -> Path:
    return Path(config.DATA) / "_backups"


def run_backup(now: datetime | None = None) -> Path:
    """tar.gz of DATA (minus _backups/tmp/cache). SQLite files are copied with the online backup API
    first, so a half-written database is never archived. Writes to a .part file, then renames."""
    data = Path(config.DATA); out = backup_dir(); out.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now(TZ)).astimezone(TZ).strftime("%Y%m%d-%H%M")
    final = out / f"data-{stamp}.tgz"; part = final.with_suffix(".tgz.part")
    snap = out / ".sqlite-snap"; shutil.rmtree(snap, ignore_errors=True); snap.mkdir()
    try:
        with tarfile.open(part, "w:gz", compresslevel=6) as tar:
            for p in sorted(data.rglob("*")):
                rel = p.relative_to(data)
                if not p.is_file() or rel.parts[0] in SKIP_DIRS:
                    continue
                if p.suffix in (".sqlite3", ".sqlite", ".db"):
                    copy = snap / rel.name
                    src = sqlite3.connect(f"file:{p}?mode=ro", uri=True); dst = sqlite3.connect(copy)
                    try: src.backup(dst)
                    finally: src.close(); dst.close()
                    tar.add(copy, arcname=str(rel))
                elif p.suffix not in (".part", ".tmp"):
                    try: tar.add(p, arcname=str(rel))
                    except FileNotFoundError: pass        # deleted mid-run (an expired file); fine
        os.chmod(part, 0o600); part.replace(final)
    finally:
        shutil.rmtree(snap, ignore_errors=True); part.unlink(missing_ok=True)
    for old in sorted(out.glob("data-*.tgz"))[:-KEEP]:
        old.unlink(missing_ok=True)
    log.info("nightly backup %s (%d bytes)", final.name, final.stat().st_size)
    return final


def _run(job: str):
    if job == "retention":
        from . import retention
        retention.purge_expired()
    elif job == "backup" and os.environ.get("ZEIM_NIGHTLY_BACKUP", "1") != "0":
        run_backup()


def start_background():
    def loop():
        try: os.nice(10)                                  # yield the CPU to user requests
        except Exception: pass
        while True:
            now = datetime.now(TZ)
            when, job = min((next_run(now, h, m), j) for h, m, j in JOBS)
            time.sleep(max(1.0, (when - now).total_seconds()))
            try: _run(job)
            except Exception: log.exception("off-peak job %s failed", job)
    t = threading.Thread(target=loop, name="zeim-offpeak", daemon=True); t.start()
    return t
