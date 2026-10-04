#!/usr/bin/env bash
# PROPOSAL - ZEIM restore from a set created by backup.sh.
#
# Usage:
#   ./restore.sh <backup-set-dir>                 # DRY RUN / restore drill: verify + extract into a scratch dir
#   ./restore.sh <backup-set-dir> --apply         # replace live data/ and outputs/ (app must be stopped)
#
# Env: ZEIM_HOST_DIR (default /srv/zeim), AGE_IDENTITY (path to age secret key, needed for *.age sets),
#      RESTORE_TO (scratch dir for the dry run; default a new mktemp dir)
#
# --apply moves the current data/ and outputs/ aside to <name>.pre-restore-<timestamp> (it never deletes them).
set -euo pipefail
umask 077

SET="${1:-}"; MODE="${2:-}"
[ -d "$SET" ] || { echo "usage: $0 <backup-set-dir> [--apply]" >&2; exit 2; }
HOST_DIR="${ZEIM_HOST_DIR:-/srv/zeim}"
log() { printf '%s restore: %s\n' "$(date -u +%FT%TZ)" "$*"; }
die() { log "ERROR: $*"; exit 1; }

# 1. verify checksums
( cd "$SET" && sha256sum -c SHA256SUMS ) || die "checksum verification failed - do not use this set"
log "checksums ok"

# 2. extract into a scratch dir (always)
STAGE="${RESTORE_TO:-$(mktemp -d /tmp/zeim-restore.XXXXXX)}"
mkdir -p "$STAGE/data" "$STAGE/outputs"
unpack() {  # file dest
  case "$1" in
    *.age) [ -n "${AGE_IDENTITY:-}" ] || die "set is encrypted; set AGE_IDENTITY"
           age -d -i "$AGE_IDENTITY" "$1" | gzip -dc | tar -C "$2" -xf - ;;
    *)     gzip -dc "$1" | tar -C "$2" -xf - ;;
  esac
}
for f in "$SET"/data.tar.gz*;    do [ -e "$f" ] && unpack "$f" "$STAGE/data"; done
for f in "$SET"/sqlite.tar.gz*;  do [ -e "$f" ] && unpack "$f" "$STAGE/data"; done   # overlays consistent DB copies
for f in "$SET"/outputs.tar.gz*; do [ -e "$f" ] && unpack "$f" "$STAGE/outputs"; done

# 3. sanity checks: every SQLite file passes integrity_check; JSON files parse
bad=0
while IFS= read -r -d '' db; do
  [ "$(head -c 15 "$db")" = "SQLite format 3" ] || continue
  r="$(python3 -c 'import sqlite3,sys;print(sqlite3.connect(sys.argv[1]).execute("pragma integrity_check").fetchone()[0])' "$db")"
  [ "$r" = ok ] || { log "sqlite integrity FAILED: $db"; bad=1; }
done < <(find "$STAGE/data" -type f \( -name '*.db' -o -name '*.sqlite' -o -name '*.sqlite3' \) -print0)
while IFS= read -r -d '' j; do
  python3 -c 'import json,sys;json.load(open(sys.argv[1]))' "$j" 2>/dev/null || { log "invalid JSON: $j"; bad=1; }
done < <(find "$STAGE/data" -type f -name '*.json' -print0)
[ "$bad" = 0 ] || die "sanity checks failed (extracted copy left in $STAGE)"
log "extracted + verified: $STAGE ($(find "$STAGE/data" -type f | wc -l) data files, $(find "$STAGE/outputs" -type f | wc -l) output files)"

if [ "$MODE" != "--apply" ]; then
  log "DRY RUN only. Inspect $STAGE, or re-run with --apply to put it live."
  exit 0
fi

# 4. apply: app must be stopped (otherwise it would write into a half-swapped tree)
if command -v docker >/dev/null && docker ps --format '{{.Names}}' 2>/dev/null | grep -qE '^zeim-app-'; then
  die "app container is running: docker compose -f reports/deploy/docker-compose.yml stop app"
fi
TS="$(date -u +%Y%m%dT%H%M%SZ)"
for d in data outputs; do
  [ -d "$HOST_DIR/$d" ] && mv "$HOST_DIR/$d" "$HOST_DIR/$d.pre-restore-$TS"
  mv "$STAGE/$d" "$HOST_DIR/$d"
done
# Same uid/gid as the container user. Skipped (with a note) when not root.
if [ "$(id -u)" = 0 ]; then chown -R 10001:10001 "$HOST_DIR/data" "$HOST_DIR/outputs"; else log "not root: run 'chown -R 10001:10001 $HOST_DIR/data $HOST_DIR/outputs' if needed"; fi
log "restored into $HOST_DIR (previous state kept as *.pre-restore-$TS). Start the app and check /."
