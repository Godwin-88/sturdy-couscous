#!/usr/bin/env bash
# dev.sh — Start databases in Docker, API and frontend on the host
# Usage: ./dev.sh [--no-frontend] [--stop]
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB_SERVICES="memgraph postgres redis"

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
log()  { echo -e "${CYAN}[dev]${RESET} $*"; }
ok()   { echo -e "${GREEN}[ok]${RESET}  $*"; }
warn() { echo -e "${YELLOW}[warn]${RESET} $*"; }
die()  { echo -e "${RED}[err]${RESET}  $*" >&2; exit 1; }

# ── Stop mode ─────────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--stop" ]]; then
  log "Stopping any Docker containers that might own ports 8000/5173…"
  docker stop graphalpha-api graphalpha-frontend graphalpha-agent 2>/dev/null || true
  log "Stopping Docker databases…"
  docker compose -f "$REPO/docker-compose.yml" stop $DB_SERVICES 2>/dev/null || true
  log "Killing host processes on ports 8000 and 5173…"
  lsof -ti:8000 | xargs -r kill -9 2>/dev/null || true
  lsof -ti:5173 | xargs -r kill -9 2>/dev/null || true
  ok "All dev services stopped."
  exit 0
fi

NO_FRONTEND=false
[[ "${1:-}" == "--no-frontend" ]] && NO_FRONTEND=true

# ── Preflight checks ──────────────────────────────────────────────────────────
command -v docker   >/dev/null || die "docker not found"
command -v python3  >/dev/null || die "python3 not found"
command -v npm      >/dev/null || die "npm not found"
[[ -f "$REPO/.env" ]] || die ".env file not found at $REPO/.env"

# ── Override host-only env vars (databases on localhost, not docker hostnames) ─
export MEMGRAPH_HOST=localhost
export MEMGRAPH_PORT=7687
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export REDIS_HOST=localhost
export REDIS_PORT=6379

# Load the rest of .env (skips lines that are comments or already set above)
set -o allexport
# shellcheck disable=SC1090
source <(grep -v '^\s*#' "$REPO/.env" | grep -v '^\s*$' \
  | grep -vE '^(MEMGRAPH_HOST|MEMGRAPH_PORT|POSTGRES_HOST|POSTGRES_PORT|REDIS_HOST|REDIS_PORT)=')
set +o allexport

# ── 1. Start database containers ─────────────────────────────────────────────
log "Starting database containers: ${BOLD}$DB_SERVICES${RESET}"
docker compose -f "$REPO/docker-compose.yml" up -d $DB_SERVICES

# ── 2. Wait for databases to be healthy ──────────────────────────────────────
wait_healthy() {
  local name="$1" max=60 i=0
  log "Waiting for ${BOLD}$name${RESET} to be healthy…"
  while true; do
    status=$(docker inspect --format='{{.State.Health.Status}}' "$name" 2>/dev/null || echo "missing")
    [[ "$status" == "healthy" ]] && { ok "$name is healthy"; return; }
    (( i++ >= max )) && die "$name did not become healthy after ${max}s"
    sleep 2
  done
}
wait_healthy graphalpha-memgraph
wait_healthy graphalpha-postgres
wait_healthy graphalpha-redis

# ── 3. Set up API virtualenv and install dependencies ────────────────────────
VENV="$REPO/api/.venv"
PYTHON="$VENV/bin/python"

if [[ ! -f "$VENV/bin/python" ]] || ! "$VENV/bin/python" --version >/dev/null 2>&1; then
  log "Creating Python virtualenv at api/.venv…"
  python3 -m venv "$VENV"
  ok "Virtualenv created"
fi

# Install requirements only if uvicorn is missing (i.e. fresh venv or never installed)
if ! "$VENV/bin/python" -c "import uvicorn" 2>/dev/null; then
  log "Installing API dependencies (api/requirements.txt)…"
  "$VENV/bin/pip" install --quiet --upgrade pip \
    || warn "pip upgrade failed — continuing with existing pip"
  # psycopg2-binary may need libpq-dev on Python 3.14+ (no pre-built wheel)
  if ! "$VENV/bin/pip" install --quiet -r "$REPO/api/requirements.txt" 2>/dev/null; then
    warn "pip install failed — trying with libpq-dev (may need sudo)"
    sudo apt-get install -y libpq-dev 2>/dev/null || true
    "$VENV/bin/pip" install --quiet -r "$REPO/api/requirements.txt" \
      || die "Failed to install API requirements — check network and try again"
  fi
  ok "API dependencies installed"
else
  ok "API dependencies already installed — skipping pip"
fi

# yfinance is used by routes/market.py — install separately so a network failure
# here doesn't block the API from starting (market quotes will just 503)
if ! "$VENV/bin/python" -c "import yfinance" 2>/dev/null; then
  log "Installing yfinance…"
  "$VENV/bin/pip" install --quiet yfinance \
    || warn "yfinance install failed — market quotes endpoint will be unavailable"
fi

# ── 4. Start FastAPI on the host ─────────────────────────────────────────────
API_LOG="$REPO/api/dev-api.log"
log "Starting FastAPI (host) → http://localhost:8000  [log: api/dev-api.log]"

# Stop any Docker container holding port 8000, then kill any host process
docker stop graphalpha-api graphalpha-frontend graphalpha-agent 2>/dev/null || true
lsof -ti:8000 | xargs -r kill -9 2>/dev/null || true
sleep 1  # let the port fully release

(
  cd "$REPO/api"
  $PYTHON -m uvicorn main:app \
    --host 0.0.0.0 --port 8000 \
    --reload \
    --reload-exclude ".venv" \
    --reload-exclude "*.pyc" \
    >"$API_LOG" 2>&1
) &
API_PID=$!
echo "$API_PID" > "$REPO/api/.dev-pid"
ok "API started (PID $API_PID)"

# Wait until port 8000 is accepting connections (max 30s)
log "Waiting for API to accept connections…"
for i in $(seq 1 30); do
  if bash -c "cat /dev/null > /dev/tcp/localhost/8000" 2>/dev/null; then
    ok "API is up → http://localhost:8000/docs"; break
  fi
  (( i == 30 )) && { warn "API didn't start in 30s — check api/dev-api.log"; }
  sleep 1
done

# ── 5. Start Vite dev server on the host ─────────────────────────────────────
if [[ "$NO_FRONTEND" == false ]]; then
  FRONTEND_LOG="$REPO/frontend/dev-frontend.log"

  if [[ ! -d "$REPO/frontend/node_modules" ]]; then
    log "Installing frontend npm dependencies…"
    (cd "$REPO/frontend" && npm install --silent)
    ok "npm dependencies ready"
  fi

  log "Starting Vite frontend (host) → http://localhost:5173  [log: frontend/dev-frontend.log]"

  lsof -ti:5173 | xargs -r kill -9 2>/dev/null || true

  (
    cd "$REPO/frontend"
    VITE_API_URL=http://localhost:8000 npm run dev \
      >"$FRONTEND_LOG" 2>&1
  ) &
  FE_PID=$!
  echo "$FE_PID" > "$REPO/frontend/.dev-pid"
  ok "Frontend started (PID $FE_PID)"

  log "Waiting for Vite to be ready…"
  for i in $(seq 1 30); do
    if bash -c "cat /dev/null > /dev/tcp/localhost/5173" 2>/dev/null; then
      ok "Frontend is up → http://localhost:5173"; break
    fi
    (( i == 30 )) && warn "Vite didn't start in 30s — check frontend/dev-frontend.log"
    sleep 1
  done
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${BOLD}  GraphAlpha dev environment ready${RESET}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "  Frontend   : ${GREEN}http://localhost:5173${RESET}"
echo -e "  API docs   : ${GREEN}http://localhost:8000/docs${RESET}"
echo -e "  Memgraph   : ${GREEN}bolt://localhost:7687${RESET}  Lab: ${GREEN}http://localhost:3000${RESET}"
echo -e "  PostgreSQL : ${GREEN}localhost:5432${RESET}"
echo -e "  Redis      : ${GREEN}localhost:6379${RESET}"
echo ""
echo -e "  Stop all   : ${YELLOW}./dev.sh --stop${RESET}"
echo -e "  API log    : ${YELLOW}tail -f api/dev-api.log${RESET}"
[[ "$NO_FRONTEND" == false ]] && \
echo -e "  FE log     : ${YELLOW}tail -f frontend/dev-frontend.log${RESET}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"

# Keep script alive so Ctrl-C kills children cleanly
trap './dev.sh --stop 2>/dev/null; exit 0' INT TERM
wait
