#!/usr/bin/env bash
# Start the TEMPORARY passcode-protected HTTPS test address for ZEIM. UNTESTED ON REAL iOS.
#   ./start.sh --haruto-confirmed [--max-minutes 120] [--snapshot]
# Refuses to run without --haruto-confirmed (Haruto must have confirmed in HQ that S-01, signed-link/base-URL
# and the camera-button fixes are live). Never prints the passcode or the URL; they are saved 0600 in the run dir.
#   --snapshot   run the last COMMITTED code (git archive HEAD) instead of the working tree
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/lib.sh"

CONFIRMED=0; SNAPSHOT=0
while [ $# -gt 0 ]; do
  case "$1" in
    --haruto-confirmed) CONFIRMED=1 ;;
    --snapshot) SNAPSHOT=1 ;;
    --max-minutes) shift; MAX_MINUTES="${1:-}" ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac; shift
done
if [ "$CONFIRMED" != 1 ]; then
  echo "REFUSING TO START: pass --haruto-confirmed only after Haruto has confirmed in HQ that the first-batch fixes (S-01 settings gate, signed-link/base-URL, camera button) are live." >&2
  exit 3
fi
case "$MAX_MINUTES" in ''|*[!0-9]*) echo "--max-minutes must be a whole number" >&2; exit 2 ;; esac
[ "$MAX_MINUTES" -ge 5 ] && [ "$MAX_MINUTES" -le 480 ] || { echo "--max-minutes must be 5..480" >&2; exit 2; }

for b in "$ZEIM_CADDY" "$ZEIM_CLOUDFLARED" "$ZEIM_PYTHON"; do [ -x "$b" ] || { echo "missing executable: $b" >&2; exit 4; }; done
command -v ss >/dev/null && command -v curl >/dev/null && command -v setsid >/dev/null || { echo "need ss, curl, setsid" >&2; exit 4; }

# Already running? Then stop it first (one test at a time).
if [ -L "$CURRENT" ] || [ -e "$CURRENT" ]; then
  if [ -f "$CURRENT/pids/caddy.pid" ] && alive "$(cat "$CURRENT/pids/caddy.pid" 2>/dev/null)"; then
    echo "A test run is already active ($(readlink -f "$CURRENT")). Run ./stop.sh first." >&2; exit 5
  fi
fi
for p in "$PROXY_PORT" "$APP_PORT"; do port_busy "$p" && { echo "port $p is already in use; choose another with ZEIM_PROXY_PORT / ZEIM_APP_PORT" >&2; exit 5; }; done

# Sanity: the fixes the gate is about must at least exist in the code we are about to run (read-only check).
SRC="$ZEIM_APP_DIR"
if [ "$SNAPSHOT" = 1 ]; then :; else
  grep -q "PHOTO3D_PUBLIC_BASE_URL" "$SRC/app/config.py" && grep -q "require_settings_admin" "$SRC/app/api/guards.py" \
    || { echo "app code lacks PHOTO3D_PUBLIC_BASE_URL / settings gate - not starting" >&2; exit 6; }
fi

umask 077
TS="$(date +%Y%m%d-%H%M%S)"
RUN="$RUN_ROOT/$TS"
mkdir -p "$RUN"/{data,outputs,logs,pids}
chmod 700 "$RUN" "$RUN_ROOT"
ln -sfn "$RUN" "$CURRENT"

if [ "$SNAPSHOT" = 1 ]; then
  mkdir -p "$RUN/app-snapshot"
  git -C "$ZEIM_APP_DIR" archive HEAD | tar -x -C "$RUN/app-snapshot"
  SRC="$RUN/app-snapshot"
fi
{ echo "app_dir=$SRC"; echo "git_head=$(git -C "$ZEIM_APP_DIR" rev-parse --short HEAD 2>/dev/null || echo ?)";
  echo "working_tree_dirty_app_static=$(git -C "$ZEIM_APP_DIR" status --short -- app static 2>/dev/null | wc -l)";
  echo "max_minutes=$MAX_MINUTES"; echo "started=$(date -Is)"; } > "$RUN/run-info.txt"

fail() { echo "start failed: $1 - stopping everything" >&2; "$DIR/stop.sh" --quiet || true; exit 1; }

# ---- passcode (never echoed) + bcrypt hash ----
"$ZEIM_PYTHON" - > "$RUN/passcode.txt" <<'PY'
import secrets
a = "abcdefghjkmnpqrstuvwxyz23456789"          # no look-alike characters (i l o 0 1)
g = ["".join(secrets.choice(a) for _ in range(5)) for _ in range(5)]
print("-".join(g), end="")                      # 25 chars, ~120 bits
PY
chmod 600 "$RUN/passcode.txt"
# caddy hash-password reads one line from stdin (needs the newline); the passcode never appears on a command line
HASH="$({ cat "$RUN/passcode.txt"; echo; } | "$ZEIM_CADDY" hash-password 2>/dev/null | head -n1 || true)"
case "$HASH" in '$2'*) ;; *) fail "could not make the password hash" ;; esac
printf '%s' "$HASH" > "$RUN/auth.hash"; chmod 600 "$RUN/auth.hash"

# ---- Caddy config ----
sed -e "s|@@RUN@@|$RUN|g" -e "s|@@PROXY_PORT@@|$PROXY_PORT|g" -e "s|@@APP_PORT@@|$APP_PORT|g" -e "s|@@USER@@|$AUTH_USER|g" \
  "$DIR/Caddyfile.template" > "$RUN/Caddyfile"
export ZEIM_AUTH_HASH="$HASH"
"$ZEIM_CADDY" validate --config "$RUN/Caddyfile" --adapter caddyfile >"$RUN/logs/caddy-validate.log" 2>&1 || fail "Caddy config invalid"

# ---- 1. Caddy (127.0.0.1 only) ----
setsid nohup "$ZEIM_CADDY" run --config "$RUN/Caddyfile" --adapter caddyfile >"$RUN/logs/caddy-stdout.log" 2>&1 < /dev/null &
echo $! > "$RUN/pids/caddy.pid"
unset ZEIM_AUTH_HASH
for _ in $(seq 1 20); do port_busy "$PROXY_PORT" && break; sleep 0.5; done
port_busy "$PROXY_PORT" || fail "Caddy did not start"

# ---- 2. tunnel -> Caddy only ----
# cloudflared talks to Cloudflare on port 7844 (not 443). Some sandboxes block that; warn early (not fatal: it may use UDP).
if [ "${ZEIM_SKIP_EDGE_PRECHECK:-0}" != 1 ] && ! timeout 6 bash -c 'echo > /dev/tcp/region1.v2.argotunnel.com/7844' 2>/dev/null; then
  echo "WARNING: TCP port 7844 to Cloudflare looks blocked from this computer; the tunnel may not connect (see RUNBOOK 'If the tunnel will not start')." >&2
fi
: > "$RUN/cloudflared-empty-config.yml"
setsid nohup "$ZEIM_CLOUDFLARED" tunnel --no-autoupdate --config "$RUN/cloudflared-empty-config.yml" \
  --url "http://127.0.0.1:$PROXY_PORT" >"$RUN/logs/cloudflared.log" 2>&1 < /dev/null &
echo $! > "$RUN/pids/cloudflared.pid"
URL=""
for _ in $(seq 1 60); do
  URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$RUN/logs/cloudflared.log" 2>/dev/null | head -n1 || true)"
  [ -n "$URL" ] && break
  alive "$(cat "$RUN/pids/cloudflared.pid")" || fail "cloudflared exited (see $RUN/logs/cloudflared.log)"
  sleep 1
done
[ -n "$URL" ] || fail "no tunnel address after 60 s"
printf '%s' "$URL" > "$RUN/url.txt"; chmod 600 "$RUN/url.txt"

# ---- 3. ZEIM on 127.0.0.1, fresh data folders, base URL = the tunnel address ----
(
  cd "$SRC"
  export HOST=127.0.0.1 PORT="$APP_PORT"
  export PHOTO3D_DATA="$RUN/data" PHOTO3D_OUT="$RUN/outputs"
  export PHOTO3D_MODE=shared                 # settings/printers/linked accounts locked (needs admin token, which is NOT set)
  export PHOTO3D_PUBLIC_BASE_URL="$URL"      # join QR codes + signed links use the tunnel address; locked in the UI
  unset PHOTO3D_ADMIN_TOKEN
  # no uvicorn access log, so signed-link URLs (/f/<token>/...) are never written to the app log
  setsid nohup "$ZEIM_PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$APP_PORT" --no-access-log \
    --proxy-headers --forwarded-allow-ips 127.0.0.1 >"$RUN/logs/app.log" 2>&1 < /dev/null &
  echo $! > "$RUN/pids/app.pid"
)
for _ in $(seq 1 40); do
  curl -fsS --max-time 2 "http://127.0.0.1:$APP_PORT/healthz" >/dev/null 2>&1 && break
  alive "$(cat "$RUN/pids/app.pid")" || fail "ZEIM exited (see $RUN/logs/app.log)"
  sleep 0.5
done
curl -fsS --max-time 2 "http://127.0.0.1:$APP_PORT/healthz" >/dev/null 2>&1 || fail "ZEIM did not become healthy"

# ---- 4. safety checks: the gate must work, locally and at the public address ----
# credentials go through a 0600 curl config file, never the command line
printf 'user = "%s:%s"\n' "$AUTH_USER" "$(cat "$RUN/passcode.txt")" > "$RUN/.curlrc"; chmod 600 "$RUN/.curlrc"
code_noauth="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:$PROXY_PORT/healthz" || true)"
code_auth="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 -K "$RUN/.curlrc" "http://127.0.0.1:$PROXY_PORT/healthz" || true)"
rm -f "$RUN/.curlrc"
[ "$code_noauth" = 401 ] || fail "local gate check: expected 401 without passcode, got $code_noauth"
[ "$code_auth" = 200 ] || fail "local gate check: expected 200 with passcode, got $code_auth"
pub=""
# ZEIM_SKIP_PUBLIC_CHECK=1 is for offline tests with a stand-in tunnel only (there is no real public address to ask)
for _ in $(seq 1 15); do
  [ "${ZEIM_SKIP_PUBLIC_CHECK:-0}" = 1 ] && { pub=skipped; break; }
  pub="$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "$URL/healthz" || true)"
  [ "$pub" = 401 ] && break
  [ "$pub" = 200 ] && fail "PUBLIC address answered 200 WITHOUT a passcode"
  sleep 2
done
PUBNOTE="public gate check: 401 without passcode (OK)"
[ "$pub" = skipped ] && PUBNOTE="public gate check skipped (test mode)"
[ "$pub" = 401 ] || [ "$pub" = skipped ] || PUBNOTE="WARNING public gate check could not be completed (last status ${pub:-none}); try the address from your phone data connection"
echo "$PUBNOTE" > "$RUN/gate-check.txt"

# ---- 5. auto-shutoff timer ----
setsid nohup bash -c "sleep ${ZEIM_TEST_TIMER_SECONDS:-$((MAX_MINUTES*60))}; exec '$DIR/stop.sh' --from-timer" >"$RUN/logs/timer.log" 2>&1 < /dev/null &
echo $! > "$RUN/pids/timer.pid"
echo "auto_shutoff=$(date -d "+$MAX_MINUTES minutes" -Is)" >> "$RUN/run-info.txt"

echo "started; URL and passcode saved in $RUN/url.txt and $RUN/passcode.txt (0600). Username: $AUTH_USER. $PUBNOTE. Auto-shutoff in $MAX_MINUTES min."
