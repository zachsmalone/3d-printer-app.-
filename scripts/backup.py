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

Encryption at rest: pass --encrypt-to <AGE_RECIPIENT> (or set ZEIM_BACKUP_AGE_RECIPIENT) and
the plaintext directory is replaced by zeim-<ts>.tar.age — an `age`-encrypted tarball of itself.
The plaintext copy is removed only after the encrypted archive exists and is non-empty; if
`age` is missing or fails, the run FAILS LOUDLY (exit 1) — encrypted mode never silently falls
back to a plaintext backup. Off-site delivery stays a separate step (docs/ops/backup-restore.md).

Usage:
  python -m scripts.backup --data data --out outputs --backup-root backups
  python -m scripts.backup --data data --out outputs --backup-root backups --encrypt-to age1...
"""
from __future__ import annotations

import argparse
import os
import hashlib
import json
import shutil
import sqlite3
import time
from pathlib import Path

DAILY_KEEP = 14
WEEKLY_KEEP = 8


def _ts_of(path: Path) -> str:
    """zeim-YYYYMMDD-HHMMSS[.tar.age] -> YYYYMMDD-HHMMSS."""
    return path.name.split(".")[0].split("-")[-1]


def _age_encrypt_dir(backup_dir: Path, recipient: str) -> Path:
    """tar+age the plaintext backup into <dir>.tar.age, then remove the plaintext dir.
    Raises on any failure — encrypted mode never silently falls back to plaintext."""
    import subprocess
    if not shutil.which("age"):
        raise RuntimeError("age binary not found — install age (e.g. apt install age) or drop --encrypt-to")
    archive = backup_dir.parent / f"{backup_dir.name}.tar.age"
    # tar from a pipe so no plaintext archive ever exists on disk
    cmd = ["tar", "-cf", "-", "-C", str(backup_dir.parent), backup_dir.name]
    enc = ["age", "-e", "-r", recipient]
    with open(archive, "wb") as out:
        tar_p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        age_p = subprocess.Popen(enc, stdin=tar_p.stdout, stdout=out, stderr=subprocess.PIPE)
        tar_p.stdout.close()
        _, err = age_p.communicate()
        tar_p.wait()
    if age_p.returncode != 0 or tar_p.returncode != 0 or not archive.exists() or archive.stat().st_size == 0:
        archive.unlink(missing_ok=True)
        raise RuntimeError(f"age encryption failed: {err.decode(errors='replace')[:400]}")
    shutil.rmtree(backup_dir)          # plaintext exists no more
    return archive


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


def create_backup(data_dir: Path, out_dir: Path, backup_root: Path, now: float | None = None,
                  encrypt_to: str | None = None) -> dict:
    """Make one timestamped backup. Returns a report dict (never raises for missing pieces).
    With encrypt_to (an age recipient): the plaintext dir becomes <dir>.tar.age — failure to
    encrypt raises (never a silent plaintext backup)."""
    now = time.time() if now is None else now
    ts = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
    backup_dir = backup_root / f"zeim-{ts}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_dir.chmod(0o700)                     # plaintext snapshots are private

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
    if encrypt_to:
        archive = _age_encrypt_dir(backup_dir, encrypt_to)
        report["encrypted"] = True
        report["archive"] = str(archive)
    return report


def _is_sunday(path: Path) -> bool:
    ts = _ts_of(path)  # zeim-YYYYMMDD-HHMMSS[.tar.age]
    try:
        return time.strptime(ts[:8], "%Y%m%d").tm_wday == 6
    except ValueError:
        return False


def enforce_retention(backup_root: Path, now: float | None = None,
                      daily_keep: int = DAILY_KEEP, weekly_keep: int = WEEKLY_KEEP) -> dict:
    """Keep the newest `daily_keep` daily backups and `weekly_keep` weekly (Sunday) backups.
    Works for both plaintext directories and .tar.age archives."""
    now = time.time() if now is None else now
    backups = sorted(p for p in backup_root.glob("zeim-*") if p.is_dir() or p.name.endswith(".tar.age"))
    weekly = [p for p in backups if _is_sunday(p)][-weekly_keep:]
    keep = set(backups[-daily_keep:]) | set(weekly)
    removed = [p for p in backups if p not in keep]
    for p in removed:
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        else:
            p.unlink(missing_ok=True)
    return {"kept": len(backups) - len(removed), "removed": len(removed)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ZEIM daily backup (DB snapshots + JSON + outputs manifest)")
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="outputs")
    ap.add_argument("--backup-root", default="backups")
    ap.add_argument("--encrypt-to", default=os.environ.get("ZEIM_BACKUP_AGE_RECIPIENT", ""),
                    help="age recipient (public key): replace the plaintext dir with a .tar.age archive")
    args = ap.parse_args(argv)
    try:
        report = create_backup(Path(args.data), Path(args.out), Path(args.backup_root),
                               encrypt_to=args.encrypt_to or None)
    except RuntimeError as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1
    report["retention"] = enforce_retention(Path(args.backup_root))
    print(json.dumps(report, indent=1))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
