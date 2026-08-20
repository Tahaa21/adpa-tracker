#!/usr/bin/env bash
# Stops any stale ADPA Tracker backend/frontend processes left listening on
# the app's local ports (e.g. after a terminal was closed instead of using
# Ctrl+C in start.sh). Only touches ports 8000 and 5173.

set -uo pipefail

info()  { printf '\033[1;34m[stop]\033[0m %s\n' "$1"; }
ok()    { printf '\033[1;32m[stop]\033[0m %s\n' "$1"; }

if ! command -v lsof >/dev/null 2>&1; then
  echo "lsof not found — cannot detect processes by port on this system." >&2
  echo "Manually stop any running 'uvicorn app.main:app' / 'vite' processes." >&2
  exit 1
fi

found_any=false
for port in 8000 5173; do
  pids=$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
  if [[ -n "$pids" ]]; then
    found_any=true
    for pid in $pids; do
      info "Stopping process on port $port (PID $pid)..."
      kill "$pid" 2>/dev/null || true
    done
  fi
done

if [[ "$found_any" == false ]]; then
  ok "Nothing running on ports 8000 or 5173."
  exit 0
fi

sleep 1
for port in 8000 5173; do
  pids=$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
  for pid in $pids; do
    info "Force-stopping stubborn process on port $port (PID $pid)..."
    kill -9 "$pid" 2>/dev/null || true
  done
done

ok "Done."
