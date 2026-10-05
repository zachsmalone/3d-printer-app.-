#!/usr/bin/env bash
# Stop the temporary iPhone test address: app, Caddy, tunnel, timer. Then confirm nothing is still listening,
# scan the logs for signed-link tokens (counts only), and delete the passcode and URL files.
#   ./stop.sh [--no-check] [--purge-data] [--quiet] [--from-timer]
#   --keep-token  (used by start.sh when a start fails) leaves the ngrok token file in place.
#   Also shreds Zach's ngrok authtoken file (/workspace/tools/.ngrok-authtoken); Zach resets the token after the test.
#   --purge-data   also delete the test data/outputs folders (photos and models made during the test)
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/lib.sh"
CHECK=1; PURGE=0; QUIET=0; FROM_TIMER=0; KEEP_TOKEN=0
for a in "$@"; do
  case "$a" in --no-check) CHECK=0 ;; --purge-data) PURGE=1 ;; --quiet) QUIET=1 ;; --from-timer) FROM_TIMER=1 ;; --keep-token) KEEP_TOKEN=1 ;;
    *) echo "unknown option: $a" >&2; exit 2 ;; esac
done
say() { [ "$QUIET" = 1 ] || echo "$@"; }
shred_token() {
  [ -f "$NGROK_TOKEN_FILE" ] && { shred -u "$NGROK_TOKEN_FILE" 2>/dev/null || rm -f "$NGROK_TOKEN_FILE"; say "ngrok authtoken file shredded"; }
  return 0
}
[ -e "$CURRENT" ] || { say "no test run found at $CURRENT"; [ "$KEEP_TOKEN" = 1 ] || shred_token; exit 0; }
RUN="$(readlink -f "$CURRENT")"
NGROK_WAS_STARTED=0; [ -f "$RUN/pids/ngrok.pid" ] && NGROK_WAS_STARTED=1

kill_group() {   # $1 = name; each process was started with setsid, so its pid is also its process-group id
  local f="$RUN/pids/$1.pid" pid
  [ -f "$f" ] || return 0
  pid="$(cat "$f" 2>/dev/null)"
  if alive "$pid"; then
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null
    for _ in $(seq 1 20); do alive "$pid" || break; sleep 0.25; done
    alive "$pid" && { kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null; }
    say "stopped $1 (pid $pid)"
  fi
  rm -f "$f"
}
# the tunnel first, so the public address dies before anything else
kill_group ngrok
kill_group caddy
kill_group app
[ "$FROM_TIMER" = 1 ] || kill_group timer
rm -f "$RUN/pids/timer.pid"

# confirm nothing is left listening
LEFT=0
for p in "$PROXY_PORT" "$APP_PORT"; do
  if port_busy "$p"; then say "WARNING: something is still listening on port $p"; LEFT=1; fi
done
pgrep -f "$RUN/Caddyfile" >/dev/null 2>&1 && { say "WARNING: a Caddy for this run is still alive"; LEFT=1; }
pgrep -f "$RUN/ngrok.yml" >/dev/null 2>&1 && { say "WARNING: an ngrok for this run is still alive"; LEFT=1; }
port_busy 4040 && { say "WARNING: something is listening on port 4040"; LEFT=1; }
[ "$LEFT" = 0 ] && say "confirmed: nothing from this test is listening (ports $PROXY_PORT and $APP_PORT are free)"

if [ "$CHECK" = 1 ] && [ "$QUIET" = 0 ]; then
  "$DIR/check-logs.sh" "$RUN" | tee "$RUN/log-check-report.txt" || true
fi

# the public address is random per run and is not needed after the test: blank it out of the ngrok log
[ -f "$RUN/logs/ngrok.log" ] && sed -i -E 's#https://[A-Za-z0-9.-]+\.ngrok[A-Za-z.-]*#https://REDACTED.ngrok#g' "$RUN/logs/ngrok.log"
[ "$KEEP_TOKEN" = 1 ] || shred_token
for f in passcode.txt url.txt auth.hash .curlrc .pubcurl-auth .pubcurl-noauth; do
  [ -f "$RUN/$f" ] && { shred -u "$RUN/$f" 2>/dev/null || rm -f "$RUN/$f"; }
done
say "passcode, address and hash files deleted"
echo "stopped=$(date -Is)" >> "$RUN/run-info.txt"
if [ "$PURGE" = 1 ]; then rm -rf "$RUN/data" "$RUN/outputs" "$RUN/app-snapshot" "$RUN"/app-snapshot-* "$RUN"/data-prev-* "$RUN"/outputs-prev-*; say "test data and outputs deleted"
else say "test data kept in $RUN/data and $RUN/outputs (use --purge-data to delete; they may hold photos)"; fi
rm -f "$CURRENT"
[ "$LEFT" = 0 ]
