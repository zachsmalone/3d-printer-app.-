#!/usr/bin/env bash
# ZEIM code rollback on the server. Code only: user data lives in $ZEIM_HOST_DIR (/srv/zeim) and is not touched.
# For data, use restore.sh.
#
# Usage (as root on the VM):
#   rollback.sh --list                  # show backup copies of the deploy dir, newest first, with their commit
#   rollback.sh /opt/zeim.prev-<sha>-<hhmmss>   # swap that copy in, rebuild, health-check; undo itself if unhealthy
#
# Env: DEPLOY_DIR (default /opt/zeim), HEALTH_URL (default https://zeimapp.com/healthz),
#      HEALTH_TRIES (default 40, 5 s apart)
set -euo pipefail
DEPLOY="${DEPLOY_DIR:-/opt/zeim}"
URL="${HEALTH_URL:-https://zeimapp.com/healthz}"
TRIES="${HEALTH_TRIES:-40}"
COMPOSE="reports/deploy/docker-compose.yml"
log() { printf '%s rollback: %s\n' "$(date +%FT%T%z)" "$*"; }
die() { log "ERROR: $*"; exit 1; }

if [ "${1:-}" = "--list" ]; then
  ls -dt "$DEPLOY".prev-* 2>/dev/null | while read -r d; do
    printf '%s\t%s\n' "$d" "$(cut -c1-12 "$d/.deploy-sha" 2>/dev/null || echo '?')"; done
  exit 0
fi
TARGET="${1:-}"
[ -n "$TARGET" ] || { echo "usage: $0 --list | $0 <backup-dir>" >&2; exit 2; }
TARGET="${TARGET%/}"
[ -d "$TARGET" ] || die "no such dir: $TARGET"
[ "$TARGET" != "$DEPLOY" ] || die "target is the live dir"
[ -f "$TARGET/$COMPOSE" ] && [ -f "$TARGET/Dockerfile" ] || die "$TARGET does not look like a deploy dir (no compose file / Dockerfile)"
[ -f "$DEPLOY/.env" ] || die "live $DEPLOY/.env missing; refusing (the rollback reuses it)"

healthy() { for _ in $(seq "$TRIES"); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' "$URL" || true)" = 200 ] && return 0; sleep 5; done; return 1; }
up() { ( cd "$1" && docker compose -f "$COMPOSE" --env-file .env up -d --build ); }

TS="$(date +%H%M%S)"; CUR="$(cut -c1-7 "$DEPLOY/.deploy-sha" 2>/dev/null || echo unknown)"
ASIDE="$DEPLOY.rolledback-$CUR-$TS"
log "live $CUR -> $(cut -c1-7 "$TARGET/.deploy-sha" 2>/dev/null || echo '?') from $TARGET"
mv "$DEPLOY" "$ASIDE"
cp -a "$TARGET" "$DEPLOY"                    # copy, so the backup itself stays intact for another try
cp -p "$ASIDE/.env" "$DEPLOY/.env"           # keep today's secrets/flags, never an older .env
chmod 600 "$DEPLOY/.env"
grep -E '^ZEIM_(COMING_SOON|PLANS_ENABLED|2D3D_ENABLED)=' "$DEPLOY/.env" || true
up "$DEPLOY"
if healthy; then log "OK: $URL is 200. Previous live kept at $ASIDE"; exit 0; fi
log "UNHEALTHY after rollback - putting $CUR back"
rm -rf "$DEPLOY.bad-$TS"; mv "$DEPLOY" "$DEPLOY.bad-$TS"; mv "$ASIDE" "$DEPLOY"; up "$DEPLOY"
healthy && die "rollback failed; original $CUR restored and healthy" || die "rollback failed AND original unhealthy - check docker compose logs"
