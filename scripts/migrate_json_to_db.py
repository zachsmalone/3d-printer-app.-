#!/usr/bin/env python3
"""Migrate ZEIM's JSON community data + build metadata into SQLite (ZEIM_STORAGE=db).

What it does, in order:
  1. DRY RUN (default is a real run; pass --dry-run to only report).
  2. Backs up every JSON file to <data>/backups/json-backup-<ts>/ before touching anything.
  3. Imports each community JSON file into the `documents` table (keyed by file stem).
  4. Imports every outputs/<id>/meta.json into the `builds` table (indexed owner/visibility).
  5. Validates: re-reads every imported document/row and compares it to the JSON source.
  6. Optionally freezes the JSON files read-only (--freeze) so they stay as a rollback source.

Safety rules:
  * Repeat-run safe: imports are upserts; re-running reconciles rather than duplicates.
  * Ownership is PRESERVED as-is. Builds with no owner keep owner_sid NULL — this script
    never assigns them to anyone. Claiming legacy builds is a deliberate later step
    (BuildStore.claim_unowned) taken by the operator, not by the migration.
  * The JSON files are never modified or deleted by this script (only read + backed up).
  * Rollback: stop the app, set ZEIM_STORAGE=json, remove the freeze (chmod +w) — the
    untouched JSON files are the fallback.

Usage:
  python -m scripts.migrate_json_to_db --data data --out outputs [--dry-run] [--freeze]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path

# community files (stem -> default) that the app's JsonFile stores know about
COMMUNITY_FILES = (
    "users", "prefs", "projects", "moderation", "education_progress",
    "engagement", "age_blocks", "favorites", "activity", "prints", "originals_prints",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents(name TEXT PRIMARY KEY, doc TEXT NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS builds(
    id TEXT PRIMARY KEY, owner_sid TEXT, visibility TEXT NOT NULL DEFAULT 'private',
    created TEXT NOT NULL, favorite INTEGER NOT NULL DEFAULT 0, saved INTEGER NOT NULL DEFAULT 0,
    payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_builds_owner ON builds(owner_sid, created);
CREATE INDEX IF NOT EXISTS idx_builds_visibility ON builds(visibility);
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(db_path), timeout=30)
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript(_SCHEMA)
    c.commit()
    return c


def migrate(data_dir: Path, out_dir: Path, dry_run: bool = False, freeze: bool = False) -> dict:
    data_dir, out_dir = Path(data_dir), Path(out_dir)
    db_path = data_dir / "zeim.sqlite3"
    report = {"documents": {}, "builds": 0, "unowned_builds": 0, "backed_up_to": None,
              "frozen": [], "validation": "ok", "dry_run": dry_run}

    json_files = [data_dir / f"{stem}.json" for stem in COMMUNITY_FILES]
    existing = [p for p in json_files if p.exists()]
    build_metas = []
    if out_dir.exists():
        for d in sorted(out_dir.iterdir()):
            mp = d / "meta.json" if d.is_dir() else None
            if mp and mp.exists() and d.name.isalnum():
                try:
                    build_metas.append(json.loads(mp.read_text()))
                except Exception:
                    print(f"  ! skipping unreadable build metadata: {d.name}", file=sys.stderr)

    if dry_run:
        report["documents"] = {p.stem: _count(p) for p in existing}
        report["builds"] = len(build_metas)
        report["unowned_builds"] = sum(1 for m in build_metas if not m.get("owner_sid"))
        return report

    # 1. backup
    if existing:
        ts = time.strftime("%Y%m%d-%H%M%S")
        backup = data_dir / "backups" / f"json-backup-{ts}"
        backup.mkdir(parents=True, exist_ok=True)
        for p in existing:
            shutil.copy2(p, backup / p.name)
        report["backed_up_to"] = str(backup)

    c = _connect(db_path)
    try:
        # 2. documents (upsert => repeat-run safe)
        for p in existing:
            doc = json.loads(p.read_text())
            c.execute(
                "INSERT INTO documents(name, doc, updated_at) VALUES(?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET doc=excluded.doc, updated_at=excluded.updated_at",
                (p.stem, json.dumps(doc, default=str), time.time()))
            report["documents"][p.stem] = len(doc) if isinstance(doc, (list, dict)) else 1

        # 3. builds (upsert; ownership preserved as-is, NULL stays NULL)
        for meta in build_metas:
            c.execute(
                "INSERT INTO builds(id, owner_sid, visibility, created, favorite, saved, payload) "
                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET owner_sid=excluded.owner_sid, "
                "visibility=excluded.visibility, created=excluded.created, favorite=excluded.favorite, "
                "saved=excluded.saved, payload=excluded.payload",
                (meta["id"], meta.get("owner_sid"), meta.get("visibility", "private"),
                 meta.get("created", ""), int(bool(meta.get("favorite"))), int(bool(meta.get("saved"))),
                 json.dumps(meta, default=str)))
            if not meta.get("owner_sid"):
                report["unowned_builds"] += 1
        report["builds"] = len(build_metas)
        c.commit()

        # 4. validate: round-trip every imported row against its JSON source
        for p in existing:
            row = c.execute("SELECT doc FROM documents WHERE name=?", (p.stem,)).fetchone()
            if row is None or json.loads(row[0]) != json.loads(p.read_text()):
                report["validation"] = f"MISMATCH: {p.name}"
                break
        for meta in build_metas:
            row = c.execute("SELECT payload FROM builds WHERE id=?", (meta["id"],)).fetchone()
            if row is None or json.loads(row[0]) != meta:
                report["validation"] = f"MISMATCH: build {meta.get('id')}"
                break
    finally:
        c.close()

    # 5. optional freeze (JSON becomes the read-only rollback source)
    if freeze:
        for p in existing:
            try:
                p.chmod(p.stat().st_mode & ~0o222)
                report["frozen"].append(p.name)
            except OSError:
                pass
    return report


def _count(p: Path) -> int:
    try:
        d = json.loads(p.read_text())
        return len(d) if isinstance(d, (list, dict)) else 1
    except Exception:
        return -1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", default="data", help="community data directory (PHOTO3D_DATA)")
    ap.add_argument("--out", default="outputs", help="per-build files directory (PHOTO3D_OUT)")
    ap.add_argument("--dry-run", action="store_true", help="report what would be imported, change nothing")
    ap.add_argument("--freeze", action="store_true", help="after a successful migration, make the JSON files read-only (rollback source)")
    args = ap.parse_args(argv)

    report = migrate(Path(args.data), Path(args.out), dry_run=args.dry_run, freeze=args.freeze)
    print(json.dumps(report, indent=1))
    if report["validation"] != "ok":
        print("VALIDATION FAILED — the database was written but does not match the JSON source. "
              "Do not switch ZEIM_STORAGE=db until this is fixed.", file=sys.stderr)
        return 1
    if report["unowned_builds"]:
        print(f"NOTE: {report['unowned_builds']} build(s) have no owner and were left unassigned. "
              "They stay private and invisible until an operator deliberately claims them "
              "(BuildStore.claim_unowned) or they are deleted.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
