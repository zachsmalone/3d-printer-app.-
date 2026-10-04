#!/usr/bin/env bash
# OPTIONAL connectivity probe for the ngrok tunnel. Opens a public ngrok address for ~15 seconds that points at a port where nothing
# listens (127.0.0.1:9), so it can only ever answer with an ngrok error page: no ZEIM, no data, no passcode involved.
# Prints only yes/no (+ the ngrok error code on failure). Never prints or logs the authtoken or the address.
# NOTE: this uses the ngrok free-plan agent session (only one at a time), so do not run it while a test run is live.
# "yes" means ngrok logged 'started tunnel' (a real session with ngrok's servers).
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; . "$DIR/lib.sh"
[ "${1:-}" = "--yes-open-a-probe-tunnel" ] || { echo "pass --yes-open-a-probe-tunnel (see comments in this file)" >&2; exit 3; }
[ -x "$ZEIM_NGROK" ] && [ -s "$NGROK_TOKEN_FILE" ] || { echo "need $ZEIM_NGROK and the token file" >&2; exit 4; }
umask 077; T="$(mktemp -d)"
printf 'version: "3"\nagent:\n  crl_url: https://crl.ngrok-agent.com/ngrok.crl\n  web_addr: false\n  update_check: false\n  console_ui: false\n' > "$T/ngrok.yml"
( NGROK_AUTHTOKEN="$(tr -d '\r\n ' < "$NGROK_TOKEN_FILE")" setsid "$ZEIM_NGROK" http 127.0.0.1:9 --config "$T/ngrok.yml" --log=stdout --log-format=json >"$T/log" 2>&1 < /dev/null & echo $! > "$T/pid" )
P="$(cat "$T/pid")"; ok=no
for _ in $(seq 1 25); do grep -q '"msg":"started tunnel"' "$T/log" && { ok=yes; break; }; kill -0 "$P" 2>/dev/null || break; sleep 1; done
kill -TERM -- "-$P" 2>/dev/null || kill -TERM "$P" 2>/dev/null; sleep 1; kill -KILL -- "-$P" 2>/dev/null
echo "ngrok tunnel actually connected from this computer: $ok"
[ "$ok" = yes ] || grep -oE 'ERR_NGROK_[0-9]+|timed out fetching CRL|failed to dial[^"]{0,80}' "$T/log" | sort -u | head -n 3
# the log holds the address (and must never hold the token): destroy it
if [ -n "$(tr -d '\r\n ' < "$NGROK_TOKEN_FILE")" ] && [ "$(grep -cF -- "$(tr -d '\r\n ' < "$NGROK_TOKEN_FILE")" "$T/log")" != 0 ]; then echo "WARNING: token text was found in the probe log (log is being shredded)"; fi
shred -u "$T/log" 2>/dev/null; rm -rf "$T"; [ "$ok" = yes ]
