#!/usr/bin/env bash
# PROPOSAL - ZEIM backup: data/ + outputs/ (+ any SQLite DBs, safely) -> one timestamped set, with retention.
#
# Usage:   ./backup.sh                 # uses defaults / env below
# Cron:    15 3 * * *  ZEIM_HOST_DIR=/srv/zeim BACKUP_DIR=/srv/zeim-backups /opt/zeim/reports/deploy/backup.sh >>/var/log/zeim-backup.log 2>&1
#
# Env (all optional):
#   ZEIM_HOST_DIR     host dir holding data/ and outputs/          (default /srv/zeim)
#   BACKUP_DIR        where backup sets go                         (default /srv/zeim-backups)
#   KEEP_DAILY        daily sets to keep                           (default 14)
#   KEEP_WEEKLY       weekly sets (taken on Sundays) to keep       (default 8)
#   INCLUDE_OUTPUTS   1 = also archive outputs/ (default 1; builds can be regenerated, user data cannot)
#   AGE_RECIPIENT     age public key; if set, archives are encrypted with `age` (STRONGLY recommended off-site)
#   RCLONE_REMOTE     e.g. b2:zeim-backups/prod ; if set, the set is copied there with `rclone copy`
#
# NOTE: data/ contains secrets (link.key, secret.key, plain-text printer API keys in settings.json).
# A backup is therefore as sensitive as production: keep it 0600/0700, encrypt before it leaves the box.
set -euo pipefail
umask 077

HOST_DIR="${ZEIM_HOST_DIR:-/srv/zeim}"
BACKUP_DIR="${BACKUP_DIR:-/srv/zeim-backups}"
KEEP_DAILY="${KEEP_DAILY:-14}"
KEEP_WEEKLY="${KEEP_WEEKLY:-8}"
INCLUDE_OUTPUTS="${INCLUDE_OUTPUTS:-1}"
AGE_RECIPIENT="${AGE_RECIPIENT:-}"
RCLONE_REMOTE="${RCLONE_REMOTE:-}"

DATA="$HOST_DIR/data"; OUTS="$HOST_DIR/outputs"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DOW="$(date -u +%u)"                       # 7 = Sunday
KIND=daily; [ "$DOW" = 7 ] && KIND=weekly
SET="$BACKUP_DIR/$KIND/zeim-$STAMP"

log() { printf '%s backup: %s\n' "$(date -u +%FT%TZ)" "$*"; }
die() { log "ERROR: $*"; exit 1; }

[ -d "$DATA" ] || die "data dir not found: $DATA"
[ "$INCLUDE_OUTPUTS" = 1 ] && [ ! -d "$OUTS" ] && die "outputs dir not found: $OUTS"
command -v tar >/dev/null || die "tar missing"
[ -z "$AGE_RECIPIENT" ] || command -v age >/dev/null || die "AGE_RECIPIENT set but 'age' not installed"

# One backup at a time.
mkdir -p "$BACKUP_DIR"
exec 9>"$BACKUP_DIR/.lock"
flock -n 9 || die "another backup is running"

mkdir -p "$SET"
WORK="$(mktemp -d "$BACKUP_DIR/.work.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

# --- 1. SQLite databases: consistent online copy via the backup API (never cp a live DB / WAL). -------------
# The app has no SQLite yet (JSON stores). This block becomes active when Engineering adds a DB under data/.
sqlite_backup() {  # src dst
  if command -v sqlite3 >/dev/null; then
    sqlite3 "$1" ".timeout 10000" ".backup '$2'"
  else
    python3 - "$1" "$2" <<'PY'
import sqlite3, sys
src = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True, timeout=10)
dst = sqlite3.connect(sys.argv[2])
with dst:
    src.backup(dst)
dst.close(); src.close()
PY
  fi
}
mkdir -p "$WORK/sqlite"
EXCLUDES=()
while IFS= read -r -d '' db; do
  rel="${db#"$DATA"/}"
  case "$(head -c 15 "$db" 2>/dev/null)" in "SQLite format 3") ;; *) continue ;; esac
  mkdir -p "$WORK/sqlite/$(dirname "$rel")"
  sqlite_backup "$db" "$WORK/sqlite/$rel"
  [ "$(python3 -c 'import sqlite3,sys;print(sqlite3.connect(sys.argv[1]).execute("pragma integrity_check").fetchone()[0])' "$WORK/sqlite/$rel")" = ok ] \
    || die "integrity_check failed for $rel"
  EXCLUDES+=(--exclude="./$rel" --exclude="./$rel-wal" --exclude="./$rel-shm" --exclude="./$rel-journal")
  log "sqlite ok: $rel"
done < <(find "$DATA" -type f \( -name '*.db' -o -name '*.sqlite' -o -name '*.sqlite3' \) -print0)

# --- 2. data/ (JSON stores, keys, settings) ------------------------------------------------------------------
# JSON files are rewritten by the app without cross-process locking; an in-flight write can be caught
# half-written. tar's exit code 1 ("file changed as we read it") is therefore tolerated but logged.
tar_ok() { local rc=0; "$@" || rc=$?; [ "$rc" -le 1 ] || die "tar failed ($rc)"; [ "$rc" -eq 0 ] || log "warning: files changed during tar"; }
tar_ok tar -C "$DATA" "${EXCLUDES[@]}" -cf "$WORK/data.tar" .
if find "$WORK/sqlite" -type f | grep -q .; then tar -C "$WORK/sqlite" -cf "$WORK/sqlite.tar" .; fi

# --- 3. outputs/ -----------------------------------------------------------------------------------------------
if [ "$INCLUDE_OUTPUTS" = 1 ]; then tar_ok tar -C "$OUTS" -cf "$WORK/outputs.tar" .; fi

# --- 4. compress (+ optional encrypt), checksum, manifest -------------------------------------------------
for t in "$WORK"/*.tar; do
  [ -e "$t" ] || continue
  gzip -6 "$t"
  f="$t.gz"
  if [ -n "$AGE_RECIPIENT" ]; then age -r "$AGE_RECIPIENT" -o "$f.age" "$f"; rm -f "$f"; f="$f.age"; fi
  mv "$f" "$SET/"
done
{
  echo "created_utc=$STAMP"; echo "kind=$KIND"; echo "host=$(hostname)"
  echo "include_outputs=$INCLUDE_OUTPUTS"; echo "encrypted=$([ -n "$AGE_RECIPIENT" ] && echo age || echo no)"
} > "$SET/MANIFEST.txt"
( cd "$SET" && sha256sum -- *.tar.gz* MANIFEST.txt > SHA256SUMS )
log "created $SET ($(du -sh "$SET" | cut -f1))"

# --- 5. retention: keep newest KEEP_DAILY daily sets and KEEP_WEEKLY weekly sets ------------------------
prune() {  # kind keep
  local d="$BACKUP_DIR/$1" n="$2"
  [ -d "$d" ] || return 0
  ls -1d "$d"/zeim-* 2>/dev/null | sort -r | tail -n +"$((n + 1))" | while read -r old; do
    log "prune $1: $old"; rm -rf -- "$old"
  done
}
prune daily "$KEEP_DAILY"; prune weekly "$KEEP_WEEKLY"

# --- 6. optional off-site copy ----------------------------------------------------------------------------------
if [ -n "$RCLONE_REMOTE" ]; then
  command -v rclone >/dev/null || die "RCLONE_REMOTE set but rclone not installed"
  rclone copy "$SET" "$RCLONE_REMOTE/$KIND/$(basename "$SET")" --checksum
  log "uploaded to $RCLONE_REMOTE (apply bucket lifecycle rules for off-site retention)"
fi
log "done"
