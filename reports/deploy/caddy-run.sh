#!/bin/sh
# Pick the public site config. Default (unset or 0) is the full ZEIM app.
# ZEIM_COMING_SOON=1 serves the static coming-soon page (health checks still use /healthz).
set -eu
flag=$(printf '%s' "${ZEIM_COMING_SOON:-0}" | tr '[:upper:]' '[:lower:]')
dir=${CADDY_DIR:-/etc/caddy}
case "$flag" in
  1|true|yes|on) cfg="$dir/Caddyfile.coming-soon" ;;
  *) cfg="$dir/Caddyfile" ;;
esac
if [ "${ZEIM_CADDY_PRINT_CONFIG:-0}" = "1" ]; then
  printf '%s\n' "$cfg"
  exit 0
fi
cd "$(dirname "$cfg")"
exec caddy run --config "$cfg" --adapter caddyfile
