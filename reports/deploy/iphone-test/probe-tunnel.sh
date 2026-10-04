#!/usr/bin/env bash
# OPTIONAL connectivity probe - NOT run yet. Needs a go-ahead from Zach / Mr. Yami Kato because it DOES open a public
# trycloudflare.com address for about 20 seconds. The address points at a port where nothing is listening, so it can only
# ever answer with an error page: no ZEIM, no data, no passcode involved. Use it to learn whether a tunnel can work from this
# computer BEFORE the real test window. Prints only yes/no.
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; . "$DIR/lib.sh"
[ "${1:-}" = "--yes-open-a-probe-tunnel" ] || { echo "pass --yes-open-a-probe-tunnel (see comments in this file)" >&2; exit 3; }
umask 077; T="$(mktemp -d)"; : > "$T/empty.yml"
setsid "$ZEIM_CLOUDFLARED" tunnel --no-autoupdate --config "$T/empty.yml" --url http://127.0.0.1:9 >"$T/log" 2>&1 < /dev/null &
P=$!; ok=no
for _ in $(seq 1 20); do grep -qE 'https://[a-z0-9-]+\.trycloudflare\.com' "$T/log" && { ok=yes; break; }; sleep 1; done
kill -TERM -- "-$P" 2>/dev/null || kill -TERM "$P" 2>/dev/null; sleep 1; kill -KILL -- "-$P" 2>/dev/null
echo "tunnel address obtained from this computer: $ok"; [ "$ok" = yes ] || sed -E 's#https://[a-z0-9-]+\.trycloudflare\.com#<url>#g' "$T/log" | tail -n 5
rm -rf "$T"; [ "$ok" = yes ]
