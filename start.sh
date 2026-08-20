#!/usr/bin/env bash
# One-command local startup for AD Security Remediation Tracker (ADPA Tracker).
#
# LOCAL-ONLY by design: backend binds 127.0.0.1 only, frontend binds
# localhost only (no --host flag), no telemetry/external services are
# started. See docs/LOCAL_DATA_SECURITY.md.
#
# Usage: ./start.sh   (from the repo root)
# Stop:  Ctrl+C (cleans up both processes), or run ./stop.sh separately.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
VENV_DIR="$BACKEND_DIR/venv"

BACKEND_PID=""
FRONTEND_PID=""

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

info()  { printf '\033[1;34m[start]\033[0m %s\n' "$1"; }
ok()    { printf '\033[1;32m[start]\033[0m %s\n' "$1"; }
error() { printf '\033[1;31m[start]\033[0m %s\n' "$1" >&2; }

hash_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

cleanup() {
  trap - INT TERM EXIT
  echo
  info "Stopping ADPA Tracker..."
  if [[ -n "$FRONTEND_PID" ]] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    info "Stopping frontend (PID $FRONTEND_PID)..."
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    info "Stopping backend (PID $BACKEND_PID)..."
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  # Give both a moment to exit gracefully before force-killing.
  for _ in 1 2 3 4 5; do
    still_up=false
    [[ -n "$FRONTEND_PID" ]] && kill -0 "$FRONTEND_PID" 2>/dev/null && still_up=true
    [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null && still_up=true
    [[ "$still_up" == false ]] && break
    sleep 0.5
  done
  [[ -n "$FRONTEND_PID" ]] && kill -9 "$FRONTEND_PID" 2>/dev/null || true
  [[ -n "$BACKEND_PID" ]] && kill -9 "$BACKEND_PID" 2>/dev/null || true
  ok "Stopped."
}
trap cleanup INT TERM EXIT

# ---------------------------------------------------------------------------
# 1. Verify required tools
# ---------------------------------------------------------------------------

info "Checking required tools..."
missing=()
for tool in python3 node npm; do
  command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
done
if [[ ${#missing[@]} -gt 0 ]]; then
  error "Missing required tool(s): ${missing[*]}"
  error "Install them, then re-run ./start.sh."
  exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [[ "$PY_MAJOR" -lt 3 || ( "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 10 ) ]]; then
  error "python3 is version $PY_VERSION; this app requires Python 3.10+."
  exit 1
fi
ok "python3 ($PY_VERSION), node ($(node --version)), npm ($(npm --version)) found."

# ---------------------------------------------------------------------------
# 2-3. Create + activate backend venv
# ---------------------------------------------------------------------------

if [[ ! -d "$VENV_DIR" ]]; then
  info "Creating backend/venv (first run)..."
  python3 -m venv "$VENV_DIR"
else
  info "backend/venv already exists, reusing it."
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# ---------------------------------------------------------------------------
# 4. Install backend requirements only when needed
# ---------------------------------------------------------------------------

REQ_FILE="$BACKEND_DIR/requirements.txt"
REQ_STAMP="$VENV_DIR/.requirements.sha256"
CURRENT_REQ_HASH=$(hash_file "$REQ_FILE")
if [[ ! -f "$REQ_STAMP" ]] || [[ "$(cat "$REQ_STAMP")" != "$CURRENT_REQ_HASH" ]]; then
  info "Installing backend dependencies (requirements.txt changed or first run)..."
  pip install -q --upgrade pip
  pip install -q -r "$REQ_FILE"
  echo "$CURRENT_REQ_HASH" > "$REQ_STAMP"
  ok "Backend dependencies installed."
else
  info "Backend dependencies already up to date, skipping install."
fi

# ---------------------------------------------------------------------------
# 5. Install frontend dependencies only when needed
# ---------------------------------------------------------------------------

LOCK_FILE="$FRONTEND_DIR/package-lock.json"
LOCK_STAMP="$FRONTEND_DIR/node_modules/.package-lock.sha256"
if [[ -f "$LOCK_FILE" ]]; then
  CURRENT_LOCK_HASH=$(hash_file "$LOCK_FILE")
else
  CURRENT_LOCK_HASH="no-lockfile"
fi
if [[ ! -d "$FRONTEND_DIR/node_modules" ]] || [[ ! -f "$LOCK_STAMP" ]] || [[ "$(cat "$LOCK_STAMP" 2>/dev/null || true)" != "$CURRENT_LOCK_HASH" ]]; then
  info "Installing frontend dependencies (package-lock.json changed or first run)..."
  (cd "$FRONTEND_DIR" && npm install --no-fund --no-audit --loglevel=error)
  echo "$CURRENT_LOCK_HASH" > "$LOCK_STAMP"
  ok "Frontend dependencies installed."
else
  info "Frontend dependencies already up to date, skipping install."
fi

# ---------------------------------------------------------------------------
# 6. Ensure DATABASE_URL (SQLite, local-only dev database)
# ---------------------------------------------------------------------------

export DATABASE_URL="${DATABASE_URL:-sqlite:///./app.db}"
export LOCAL_ONLY="${LOCAL_ONLY:-true}"
info "DATABASE_URL=$DATABASE_URL"

# ---------------------------------------------------------------------------
# 7. Run migrations
# ---------------------------------------------------------------------------

info "Running database migrations..."
(cd "$BACKEND_DIR" && alembic upgrade head)

# ---------------------------------------------------------------------------
# 8-9. Security preflight — stop immediately on failure
# ---------------------------------------------------------------------------

info "Running local security preflight..."
if ! python3 "$SCRIPT_DIR/scripts/local_security_preflight.py"; then
  error "Security preflight FAILED — see output above."
  error "The application will NOT start until this passes. Fix the issue and re-run ./start.sh."
  exit 1
fi

# ---------------------------------------------------------------------------
# Port-conflict check (helpful pointer to stop.sh instead of a cryptic bind error)
# ---------------------------------------------------------------------------

port_busy() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -tiTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
  else
    return 1
  fi
}
if port_busy 8000 || port_busy 5173; then
  error "Port 8000 or 5173 is already in use — a previous run may still be active."
  error "Run ./stop.sh to clean it up, then re-run ./start.sh."
  exit 1
fi

# ---------------------------------------------------------------------------
# 10. Start backend on 127.0.0.1:8000 (never 0.0.0.0)
# ---------------------------------------------------------------------------

info "Starting backend on http://127.0.0.1:8000 ..."
(cd "$BACKEND_DIR" && exec uvicorn app.main:app --host 127.0.0.1 --port 8000) \
  > "$SCRIPT_DIR/.backend.log" 2>&1 &
BACKEND_PID=$!

# Wait for the backend to actually respond before starting the frontend.
for _ in $(seq 1 30); do
  if curl -s -o /dev/null "http://127.0.0.1:8000/health"; then
    break
  fi
  sleep 0.5
done
if ! curl -s -o /dev/null "http://127.0.0.1:8000/health"; then
  error "Backend did not become ready. Check .backend.log for details."
  exit 1
fi
ok "Backend is up."

# ---------------------------------------------------------------------------
# 11. Start frontend on localhost only (no --host flag => Vite default)
# ---------------------------------------------------------------------------

info "Starting frontend on http://localhost:5173 ..."
(cd "$FRONTEND_DIR" && exec ./node_modules/.bin/vite --port 5173) \
  > "$SCRIPT_DIR/.frontend.log" 2>&1 &
FRONTEND_PID=$!

for _ in $(seq 1 30); do
  if curl -s -o /dev/null "http://localhost:5173"; then
    break
  fi
  sleep 0.5
done
if ! curl -s -o /dev/null "http://localhost:5173"; then
  error "Frontend did not become ready. Check .frontend.log for details."
  exit 1
fi

# ---------------------------------------------------------------------------
# 12. Success message
# ---------------------------------------------------------------------------

echo
ok "ADPA Tracker is running at http://localhost:5173"
info "Backend API + docs: http://127.0.0.1:8000/docs"
info "Press Ctrl+C to stop."
echo

# ---------------------------------------------------------------------------
# 13-14. Keep both processes managed; clean shutdown on Ctrl+C via trap above
# ---------------------------------------------------------------------------

wait "$BACKEND_PID" "$FRONTEND_PID"
