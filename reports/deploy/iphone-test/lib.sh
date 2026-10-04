# Shared settings for the iphone-test scripts. Sourced, not run.
ZEIM_APP_DIR="${ZEIM_APP_DIR:-/workspace/photo3d}"
ZEIM_PYTHON="${ZEIM_PYTHON:-$ZEIM_APP_DIR/.venv/bin/python}"
ZEIM_CADDY="${ZEIM_CADDY:-/workspace/tools/caddy}"
ZEIM_CLOUDFLARED="${ZEIM_CLOUDFLARED:-/workspace/tools/cloudflared}"
RUN_ROOT="${ZEIM_RUN_ROOT:-/workspace/zeim-test-run}"
CURRENT="$RUN_ROOT/CURRENT"
PROXY_PORT="${ZEIM_PROXY_PORT:-8480}"      # Caddy (the only thing the tunnel talks to)
APP_PORT="${ZEIM_APP_PORT:-18765}"         # ZEIM itself, 127.0.0.1 only
AUTH_USER="${ZEIM_AUTH_USER:-zach}"
MAX_MINUTES="${ZEIM_MAX_MINUTES:-120}"

# true if something is listening on 127.0.0.1/any address at this TCP port
port_busy() { ss -H -ltn "sport = :$1" 2>/dev/null | grep -q .; }
alive() { [ -n "${1:-}" ] && kill -0 "$1" 2>/dev/null; }
