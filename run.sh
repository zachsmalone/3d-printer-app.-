#!/usr/bin/env bash
# Start photo3d in the background on port ${PORT:-8765}. Logs: server.log, pid: server.pid
cd "$(dirname "$0")"
[ -d .venv ] && source .venv/bin/activate
PORT=${PORT:-8765}
export HOST=${HOST:-127.0.0.1}   # this computer only. HOST=0.0.0.0 opens it to your network: there is NO real login yet (see README)
export PHOTO3D_MODE=${PHOTO3D_MODE:-local}   # run.sh = your own machine; servers others use should run PHOTO3D_MODE=shared (the default)
if [ -f server.pid ] && kill -0 "$(cat server.pid)" 2>/dev/null; then echo "already running (pid $(cat server.pid))"; exit 0; fi
nohup python -m uvicorn app.main:app --host "$HOST" --port "$PORT" > server.log 2>&1 &
echo $! > server.pid
[ "$HOST" != "127.0.0.1" ] && [ "$HOST" != "localhost" ] && echo "WARNING: listening on $HOST - anyone on your network can reach ZEIM, and there is no real authentication yet." | tee -a server.log
sleep 1.5; echo "photo3d on http://localhost:$PORT, bound to $HOST (pid $(cat server.pid))"
