#!/usr/bin/env python3
"""Restore a ZEIM backup and VERIFY it: checksums, DB integrity, readable data.

The monthly drill (docs/ops/backup-restore.md) is exactly this script against a copy:
  python -m scripts.restore_verify --backup backups/zeim-YYYYMMDD-HHMMSS --target /tmp/drill

What it checks before declaring the restore good:
  1. every file's sha256 matches the backup.json checksums;
  2. both databases pass PRAGMA integrity_check;
  3. the app can actually read the restored data (documents + builds via app.db).
Never run it against your live data directory unless you mean it: it OVERWRITES --target.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path


def unpack_archive(archive: Path, identity: Path) -> Path:
    """Decrypt+untar a .tar.age backup into a sibling directory, and return that directory.
    Raises on any failure (wrong identity, corrupt archive, missing age binary)."""
    import subprocess
    if not shutil.which("age"):
        raise RuntimeError("age binary not found — install age (e.g. apt install age)")
    dest = archive.parent / archive.name.replace(".tar.age", "")
    if dest.exists():
        raise RuntimeError(f"{dest} already exists — remove it first")
    with open(archive, "rb") as src:
        dec = subprocess.Popen(["age", "-d", "-i", str(identity)], stdin=src,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        untar = subprocess.Popen(["tar", "-xf", "-", "-C", str(archive.parent)],
                                stdin=dec.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        dec.stdout.close()
        _, dec_err = dec.communicate()
        untar.wait()
    if dec.returncode != 0 or untar.returncode != 0:
        shutil.rmtree(dest, ignore_errors=True)
        raise RuntimeError(f"decrypt/untar failed: {dec_err.decode(errors='replace')[:400]}")
    if not dest.is_dir():
        raise RuntimeError("archive did not contain a backup directory")
    return dest


def verify_backup(backup_dir: Path) -> dict:
    """Check a backup's internal consistency (checksums + DB integrity) without restoring."""
    result = {"checksums": "ok", "databases": {}, "ok": True}
    meta = json.loads((backup_dir / "backup.json").read_text())
    for rel, want in meta["checksums"].items():
        p = backup_dir / rel
        if not p.exists():
            result["checksums"] = f"MISSING: {rel}"
            result["ok"] = False
            break
        import hashlib
        if hashlib.sha256(p.read_bytes()).hexdigest() != want:
            result["checksums"] = f"CORRUPT: {rel}"
            result["ok"] = False
            break
    for name in ("zeim.sqlite3", "auth.sqlite3"):
        p = backup_dir / name
        if not p.exists():
            continue
        c = sqlite3.connect(str(p))
        try:
            result["databases"][name] = c.execute("PRAGMA integrity_check").fetchone()[0]
            if result["databases"][name] != "ok":
                result["ok"] = False
        finally:
            c.close()
    return result


def restore(backup_dir: Path, target_data: Path) -> dict:
    """Overwrite target_data with the backup's databases + JSON files. Outputs files are NOT
    restored here (they come from your disk/object snapshot); use --verify-outputs for that."""
    target_data.mkdir(parents=True, exist_ok=True)
    restored = {"databases": [], "json_files": []}
    for p in sorted(backup_dir.iterdir()):
        if p.name in ("zeim.sqlite3", "auth.sqlite3"):
            shutil.copy2(p, target_data / p.name)
            restored["databases"].append(p.name)
        elif p.name.endswith(".json") and p.name not in ("backup.json", "outputs.manifest.json"):
            shutil.copy2(p, target_data / p.name)
            restored["json_files"].append(p.name)
    return restored


def verify_outputs(backup_dir: Path, out_dir: Path) -> dict:
    """Compare the live outputs tree against the backup's manifest (files, sizes, checksums)."""
    manifest = json.loads((backup_dir / "outputs.manifest.json").read_text())
    import hashlib
    same, different, missing, extra = 0, [], [], []
    live = {str(p.relative_to(out_dir)): p for p in out_dir.rglob("*")
            if p.is_file() and not p.is_symlink()} if out_dir.exists() else {}
    for rel, want in manifest["files"].items():
        p = live.get(rel)
        if p is None:
            missing.append(rel)
        elif hashlib.sha256(p.read_bytes()).hexdigest() != want["sha256"]:
            different.append(rel)
        else:
            same += 1
    for rel in live:
        if rel not in manifest["files"]:
            extra.append(rel)
    ok = not different and not missing
    return {"ok": ok, "verified": same, "different": len(different),
            "missing": len(missing), "extra": len(extra)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Restore + verify a ZEIM backup")
    ap.add_argument("--backup", required=True, help="backup directory or .tar.age archive")
    ap.add_argument("--target", required=True, help="data directory to restore INTO (overwritten!)")
    ap.add_argument("--identity", default=None,
                    help="age identity file (private key) when --backup is a .tar.age archive")
    ap.add_argument("--verify-outputs", default=None, help="also check an outputs tree against the manifest")
    args = ap.parse_args(argv)

    backup_dir = Path(args.backup)
    if backup_dir.name.endswith(".tar.age"):
        if not args.identity:
            print("--identity (the age private key) is required for a .tar.age backup", file=sys.stderr)
            return 1
        try:
            backup_dir = unpack_archive(backup_dir, Path(args.identity))
        except RuntimeError as e:
            print(json.dumps({"ok": False, "error": str(e)}), file=sys.stderr)
            return 1
    v = verify_backup(backup_dir)
    print("verify:", json.dumps(v))
    if not v["ok"]:
        print("BACKUP FAILED VERIFICATION — not restoring. Take a fresh backup.", file=sys.stderr)
        return 1
    r = restore(backup_dir, Path(args.target))
    print("restored:", json.dumps(r))
    if args.verify_outputs:
        o = verify_outputs(backup_dir, Path(args.verify_outputs))
        print("outputs:", json.dumps(o))
        return 0 if o["ok"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
