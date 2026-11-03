#!/usr/bin/env bash
# ZEIM restore drill (RET5). Meant to be run once a month, by hand or by a scheduled job if Zach approves one.
# It never touches live data. It takes the newest backup set (or makes a fresh one into a scratch dir when there is
# none), runs restore.sh in dry-run mode into a scratch dir, then compares the restored copy with live:
#   - every live SQLite DB is present in the copy, passes integrity_check (restore.sh) and has the same tables,
#   - the data/ file count of the copy is within DRIFT files of live.
# Prints PASS or FAIL, appends one line to $DRILL_LOG, removes the scratch copy, exits 0 on PASS.
#
# Env: ZEIM_HOST_DIR (/srv/zeim), BACKUP_DIR (/srv/zeim-backups), DRILL_LOG ($BACKUP_DIR/restore-drill.log),
#      DRIFT (default 50), AGE_IDENTITY (for encrypted sets)
set -euo pipefail
umask 077
HERE="$(cd "$(dirname "$0")" && pwd)"
HOST_DIR="${ZEIM_HOST_DIR:-/srv/zeim}"
BACKUP_DIR="${BACKUP_DIR:-/srv/zeim-backups}"
DRIFT="${DRIFT:-50}"
log() { printf '%s drill: %s\n' "$(date -u +%FT%TZ)" "$*"; }
SCRATCH="$(mktemp -d /tmp/zeim-drill.XXXXXX)"; trap 'rm -rf "$SCRATCH"' EXIT

SET="$(ls -dt "$BACKUP_DIR"/daily/zeim-* "$BACKUP_DIR"/weekly/zeim-* 2>/dev/null | head -1 || true)"
FRESH=0
if [ -z "$SET" ]; then
  log "no backup set in $BACKUP_DIR - making a fresh one in scratch (nothing scheduled is creating backups)"
  ZEIM_HOST_DIR="$HOST_DIR" BACKUP_DIR="$SCRATCH/sets" "$HERE/backup.sh" >/dev/null
  SET="$(ls -dt "$SCRATCH"/sets/*/zeim-* | head -1)"; FRESH=1
fi
log "set: $SET"
result=FAIL; why=""
if RESTORE_TO="$SCRATCH/restored" "$HERE/restore.sh" "$SET" >"$SCRATCH/restore.out" 2>&1; then
  why="$(python3 - "$HOST_DIR/data" "$SCRATCH/restored/data" "$DRIFT" <<'PY'
import sqlite3, sys
from pathlib import Path
live, copy, drift = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
bad = []
def counts(p):
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    t = [r[0] for r in c.execute("select name from sqlite_master where type='table'")]
    return {n: c.execute(f'select count(*) from "{n}"').fetchone()[0] for n in t}
for db in live.rglob("*"):
    if db.suffix not in (".db", ".sqlite", ".sqlite3") or not db.is_file():
        continue
    rel = db.relative_to(live); r = copy / rel
    if not r.exists():
        bad.append(f"missing {rel}"); continue
    a, b = counts(db), counts(r)
    if set(b) != set(a):
        bad.append(f"{rel}: tables differ")
nl = sum(1 for f in live.rglob("*") if f.is_file()); nc = sum(1 for f in copy.rglob("*") if f.is_file())
if abs(nl - nc) > drift:
    bad.append(f"file count live {nl} vs restored {nc}")
print("; ".join(bad) if bad else f"ok ({nc} data files)")
PY
)" && case "$why" in ok*) result=PASS ;; esac
else
  why="restore.sh failed: $(tail -1 "$SCRATCH/restore.out")"
fi
line="$(date -u +%FT%TZ) $result set=$(basename "$SET")$( [ $FRESH = 1 ] && echo " (fresh)" || true) $why"
echo "$line"
LOGF="${DRILL_LOG:-$BACKUP_DIR/restore-drill.log}"
{ mkdir -p "$(dirname "$LOGF")" && echo "$line" >> "$LOGF"; } 2>/dev/null || log "could not write $LOGF"
[ "$result" = PASS ]
