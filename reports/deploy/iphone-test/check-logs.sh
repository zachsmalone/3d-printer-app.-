#!/usr/bin/env bash
# Scan a test run's logs for signed-link tokens and other secrets. Prints COUNTS only, never the values.
#   ./check-logs.sh [run-dir]        (default: the CURRENT run)
# Signed links look like  /f/<expiry>-<32 hex>/<build id>/model.<ext>  (token is in the URL PATH, see
# app/community/privacy.py make_token and app/api/printing.py). Exit code 1 if anything unredacted is found.
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/lib.sh"
RUN="$(readlink -f "${1:-$CURRENT}" 2>/dev/null || true)"
[ -n "$RUN" ] && [ -d "$RUN/logs" ] || { echo "no run dir with logs: ${1:-$CURRENT}" >&2; exit 2; }

PASS=""; [ -f "$RUN/passcode.txt" ] && PASS="$(cat "$RUN/passcode.txt")"
B64=""; [ -n "$PASS" ] && B64="$(printf '%s:%s' "$AUTH_USER" "$PASS" | base64 -w0)"
BAD=0
count() { # file, extended-regex  -> number of matching lines
  [ -f "$1" ] || { echo 0; return; }; grep -cE -- "$2" "$1" 2>/dev/null || true; }
countF() { [ -f "$1" ] && [ -n "$2" ] && { grep -cF -- "$2" "$1" 2>/dev/null || true; } || echo 0; }

echo "Log check for $(basename "$RUN") - counts of matching LINES (values are never printed)"
printf '%-24s %9s %9s %9s %9s %9s %9s\n' "log" "link-token" "bare-tok" "query?" "sens-qry" "auth-hdr" "passcode"
for f in app.log caddy-access.log caddy-runtime.log caddy-stdout.log cloudflared.log; do
  p="$RUN/logs/$f"; [ -f "$p" ] || continue
  a=$(count "$p" '/f/[0-9]{9,}-[0-9a-fA-F]{32}')          # unredacted signed-link URL
  b=$(count "$p" '[0-9]{9,}-[0-9a-f]{32}')                # token-shaped string anywhere
  q=$(count "$p" '\?[A-Za-z0-9_%.-]+=')                   # any query string at all
  s=$(count "$p" '[?&](token|sig|signature|code|state|key|api_key|password|passcode|secret|access_token)=')
  h=$(count "$p" '[Aa]uthorization.{0,6}[Bb]asic +[A-Za-z0-9+/=]{8,}')
  pw=$(countF "$p" "$PASS"); [ -n "$B64" ] && pw=$((pw + $(countF "$p" "$B64")))
  printf '%-24s %9s %9s %9s %9s %9s %9s\n' "$f" "$a" "$b" "$q" "$s" "$h" "$pw"
  # caddy-access.log is supposed to be redacted: a query string there means the redaction failed.
  if [ "$f" = caddy-access.log ]; then
    qa=$(count "$p" '\?[A-Za-z0-9_%.-]+='); [ "$qa" -gt 0 ] && BAD=1
  fi
  [ "$a" -gt 0 ] || [ "$b" -gt 0 ] || [ "$s" -gt 0 ] || [ "$h" -gt 0 ] || [ "$pw" -gt 0 ] && BAD=1
done
redacted=$(count "$RUN/logs/caddy-access.log" '/f/REDACTED/')
echo "Caddy access-log lines with a redacted signed link: $redacted"
echo "App-log lines with a redacted signed link (app/main.py RedactTokens): $(count "$RUN/logs/app.log" '/f/\[redacted\]')"
if [ -d "$RUN/data" ]; then
  n=$(grep -rIlE '[0-9]{9,}-[0-9a-f]{32}' "$RUN/data" 2>/dev/null | wc -l)
  echo "Data-folder files containing a token-shaped string: $n"
fi
echo "Note: cloudflared.log legitimately contains the random trycloudflare address; the tunnel provider and Cloudflare can see traffic. Keep logs private (run dir is mode 700)."
if [ "$BAD" = 1 ]; then echo "RESULT: FOUND token-like or credential-like values in logs (see non-zero counts). Treat the link/passcode as exposed, do not reuse, and tell Mr. Yami Kato."; exit 1; fi
echo "RESULT: no unredacted signed-link tokens, credentials or passcode found in the logs."
