#!/usr/bin/env python3
"""Daily backup for ZEIM: databases (live-safe SQLite snapshots), JSON data, outputs manifest.

What a backup contains (reports/backup.py makes one timestamped directory):
  data/zeim.sqlite3      - snapshot via SQLite's backup API (safe while the app runs)
  data/auth.sqlite3     - same, for the auth database
  data/*.json           - community JSON files (json storage mode / rollback source)
  outputs.manifest.json - EVERY build file with size + sha256 (the files stay in outputs/;
                           restoring files is from your disk/object-storage snapshot)
  backup.json           - checksums of everything above, so restore can verify integrity

Retention: keeps the newest 14 daily and 8 weekly (Sunday) backups, removes the rest.

Encryption at rest + off-site delivery are deliberately separate steps (docs/ops/backup-restore.md):
pipe the backup directory to `age` and sync it off the machine (restic/b2/rclone) from cron.

Usage:
  python -m scripts.backup --data data --out outputs --backup-root backups
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import time
from pathlib import Path

DAILY_KEEP = 14
WEEKLY_KEEP = 8


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def _snapshot_db(live: Path, dest: Path) -> bool:
    """Live-safe copy of a SQLite database using the backup API (handles WAL correctly)."""
    if not live.exists():
        return False
    src = sqlite3.connect(str(live))
    dst = sqlite3.connect(str(dest))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return True


def _outputs_manifest(out_dir: Path) -> dict:
    manifest = {"root": str(out_dir), "files": {}}
    if not out_dir.exists():
        return manifest
    for p in sorted(out_dir.rglob("*")):
        if p.is_file() and not p.is_symlink():
            manifest["files"][str(p.relative_to(out_dir))] = {
                "bytes": p.stat().st_size, "sha256": _sha256(p),
            }
    return manifest


def _checksum_dir(backup_dir: Path) -> dict:
    return {str(p.relative_to(backup_dir)): _sha256(p)
            for p in sorted(backup_dir.rglob("*")) if p.is_file() and p.name != "backup.json"}


def create_backup(data_dir: Path, out_dir: Path, backup_root: Path, now: float | None = None) -> dict:
    """Make one timestamped backup. Returns a report dict (never raises for missing pieces)."""
    now = time.time() if now is None else now
    ts = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
    backup_dir = backup_root / f"zeim-{ts}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    report = {"backup": str(backup_dir), "databases": [], "json_files": [], "output_files": 0, "ok": True}
    # 1. databases via the live-safe backup API
    for name in ("zeim.sqlite3", "auth.sqlite3"):
        dest = backup_dir / name
        if _snapshot_db(data_dir / name, dest):
            report["databases"].append(name)
    # 2. JSON data files
    for p in sorted(data_dir.glob("*.json")):
        shutil.copy2(p, backup_dir / p.name)
        report["json_files"].append(p.name)
    # 3. outputs manifest (every file, size + checksum)
    manifest = _outputs_manifest(out_dir)
    (backup_dir / "outputs.manifest.json").write_text(json.dumps(manifest, indent=1))
    report["output_files"] = len(manifest["files"])
    # 4. self-verifying checksums
    (backup_dir / "backup.json").write_text(json.dumps({
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now)),
        "checksums": _checksum_dir(backup_dir),
    }, indent=1))
    return report


def _is_sunday(path: Path) -> bool:
    ts = path.name.split("-")[-1]  # zeim-YYYYMMDD-HHMMSS
    try:
        return time.strptime(ts[:8], "%Y%m%d").tm_wday == 6
    except ValueError:
        return False


def enforce_retention(backup_root: Path, now: float | None = None,
                      daily_keep: int = DAILY_KEEP, weekly_keep: int = WEEKLY_KEEP) -> dict:
    """Keep the newest `daily_keep` daily backups and `weekly_keep` weekly (Sunday) backups."""
    now = time.time() if now is None else now
    backups = sorted(p for p in backup_root.glob("zeim-*") if p.is_dir())
    weekly = [p for p in backups if _is_sunday(p)][-weekly_keep:]
    keep = set(backups[-daily_keep:]) | set(weekly)
    removed = [p for p in backups if p not in keep]
    for p in removed:
        shutil.rmtree(p, ignore_errors=True)
    return {"kept": len(backups) - len(removed), "removed": len(removed)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ZEIM daily backup (DB snapshots + JSON + outputs manifest)")
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="outputs")
    ap.add_argument("--backup-root", default="backups")
    args = ap.parse_args(argv)
    report = create_backup(Path(args.data), Path(args.out), Path(args.backup_root))
    report["retention"] = enforce_retention(Path(args.backup_root))
    print(json.dumps(report, indent=1))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
