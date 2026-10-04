#!/usr/bin/env bash
# Start photo3d in the background on port ${PORT:-8765}. Logs: server.log, pid: server.pid
cd "$(dirname "$0")"
[ -d .venv ] && source .venv/bin/activate
PORT=${PORT:-8765}
export PHOTO3D_MODE=${PHOTO3D_MODE:-local}   # run.sh = your own machine; servers others use should run PHOTO3D_MODE=shared (the default)
if [ -f server.pid ] && kill -0 "$(cat server.pid)" 2>/dev/null; then echo "already running (pid $(cat server.pid))"; exit 0; fi
nohup python -m uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "$PORT" > server.log 2>&1 &
echo $! > server.pid
sleep 1.5; echo "photo3d on http://localhost:$PORT (pid $(cat server.pid))"
