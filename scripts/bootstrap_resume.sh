#!/usr/bin/env bash
set -euo pipefail

# scripts/bootstrap_resume.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "==> MirrorMind v1 resume bootstrap"
echo "==> Project root: $ROOT_DIR"
echo

fail() {
  echo "❌ $1" >&2
  exit 1
}

warn() {
  echo "⚠️  $1"
}

info() {
  echo "==> $1"
}

check_file() {
  local file="$1"
  [[ -f "$file" ]] || fail "Missing required file: $file"
}

check_dir() {
  local dir="$1"
  [[ -d "$dir" ]] || fail "Missing required directory: $dir"
}

info "Checking required project structure..."
check_dir "api"
check_dir "docker"
check_dir "services"
check_dir "services/avatar"
check_dir "services/tts"

check_file "docker/docker-compose.yml"
check_file "api/app/main.py"
check_file "services/avatar/app/main.py"
check_file "services/avatar/app/musetalk_wrapper.py"

if [[ ! -f ".env" ]]; then
  warn ".env not found at project root."
  if [[ -f ".env.example" ]]; then
    warn "You have .env.example. Copy it to .env and fill it in."
  fi
else
  info "Found .env"
fi

info "Creating common local directories if missing..."
mkdir -p docs
mkdir -p tmp
mkdir -p logs
mkdir -p models
mkdir -p services/avatar/cache
mkdir -p services/avatar/weights
mkdir -p services/avatar/tmp
mkdir -p services/tts/tmp

if command -v docker >/dev/null 2>&1; then
  info "Docker found: $(docker --version)"
else
  fail "Docker is not installed or not on PATH"
fi

if docker compose version >/dev/null 2>&1; then
  info "Docker Compose plugin found"
else
  fail "Docker Compose plugin not found"
fi

info "Checking compose config..."
docker compose -f docker/docker-compose.yml config >/dev/null \
  || fail "docker compose config validation failed"

AVATAR_MODE_VALUE=""
AVATAR_LOCAL_BASE_URL_VALUE=""
AVATAR_RUNPOD_BASE_URL_VALUE=""
AVATAR_BASE_URL_VALUE=""

if [[ -f ".env" ]]; then
  AVATAR_MODE_VALUE="$(grep -E '^AVATAR_MODE=' .env | tail -n1 | cut -d'=' -f2- || true)"
  AVATAR_LOCAL_BASE_URL_VALUE="$(grep -E '^AVATAR_LOCAL_BASE_URL=' .env | tail -n1 | cut -d'=' -f2- || true)"
  AVATAR_RUNPOD_BASE_URL_VALUE="$(grep -E '^AVATAR_RUNPOD_BASE_URL=' .env | tail -n1 | cut -d'=' -f2- || true)"
  AVATAR_BASE_URL_VALUE="$(grep -E '^AVATAR_BASE_URL=' .env | tail -n1 | cut -d'=' -f2- || true)"
fi

echo
info "Detected avatar configuration:"
echo "  AVATAR_MODE=${AVATAR_MODE_VALUE:-<unset>}"
echo "  AVATAR_LOCAL_BASE_URL=${AVATAR_LOCAL_BASE_URL_VALUE:-<unset>}"
echo "  AVATAR_RUNPOD_BASE_URL=${AVATAR_RUNPOD_BASE_URL_VALUE:-<unset>}"
echo "  AVATAR_BASE_URL=${AVATAR_BASE_URL_VALUE:-<unset>}"
echo

case "${AVATAR_MODE_VALUE:-}" in
  local)
    info "Local avatar mode selected"
    [[ -n "${AVATAR_LOCAL_BASE_URL_VALUE:-}" ]] || warn "AVATAR_LOCAL_BASE_URL is not set"
    ;;
  runpod)
    info "RunPod avatar mode selected"
    [[ -n "${AVATAR_RUNPOD_BASE_URL_VALUE:-}" || -n "${AVATAR_BASE_URL_VALUE:-}" ]] \
      || warn "RunPod mode is set but neither AVATAR_RUNPOD_BASE_URL nor AVATAR_BASE_URL is configured"
    ;;
  auto)
    info "Auto avatar mode selected"
    warn "Make sure your auto-resolution logic is behaving the way you expect"
    ;;
  "")
    warn "AVATAR_MODE is unset. Default behavior may surprise you."
    ;;
  *)
    warn "Unknown AVATAR_MODE value: ${AVATAR_MODE_VALUE}"
    ;;
esac

echo
info "Checking git working tree..."
if command -v git >/dev/null 2>&1; then
  git status --short || true
else
  warn "git not found; skipping working tree check"
fi

echo
info "Suggested startup commands:"
echo
echo "  Local avatar mode:"
echo "    docker compose -f docker/docker-compose.yml up -d frontend api tts avatar"
echo
echo "  RunPod avatar mode:"
echo "    docker compose -f docker/docker-compose.yml up -d frontend api tts"
echo
echo "  Tail logs:"
echo "    docker compose -f docker/docker-compose.yml logs -f api avatar tts"
echo
echo "  Check health:"
echo "    curl -s http://localhost:8000/health | jq"
echo

if [[ "${1:-}" == "--build" ]]; then
  info "Building images..."
  docker compose -f docker/docker-compose.yml build
fi

if [[ "${1:-}" == "--up-local" ]]; then
  info "Starting local stack..."
  docker compose -f docker/docker-compose.yml up -d frontend api tts avatar
fi

if [[ "${1:-}" == "--up-runpod" ]]; then
  info "Starting RunPod-routed stack..."
  docker compose -f docker/docker-compose.yml up -d frontend api tts
fi

if [[ "${1:-}" == "--health" ]]; then
  info "Checking API health..."
  curl -s http://localhost:8000/health || warn "Health check failed"
  echo
fi

info "Resume bootstrap complete."
