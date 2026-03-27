#!/usr/bin/env bash
set -euo pipefail

# scripts/dev_up.sh
# MirrorMind v1 startup helper

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
COMPOSE_FILE="$ROOT_DIR/docker/docker-compose.yml"

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

require_file() {
  [[ -f "$1" ]] || fail "Required file not found: $1"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

trim_trailing_slash() {
  local value="$1"
  echo "${value%/}"
}

validate_url_like() {
  local name="$1"
  local value="$2"
  [[ -n "$value" ]] || fail "$name is empty"
  [[ "$value" =~ ^https?:// ]] || fail "$name must start with http:// or https:// (got: $value)"
}

resolve_avatar_target() {
  if [[ -n "${AVATAR_BASE_URL:-}" ]]; then
    echo "override|${AVATAR_BASE_URL}"
    return
  fi

  case "${AVATAR_MODE:-auto}" in
    runpod)
      [[ -n "${AVATAR_RUNPOD_BASE_URL:-}" ]] || fail "AVATAR_MODE=runpod but AVATAR_RUNPOD_BASE_URL is empty"
      echo "runpod|${AVATAR_RUNPOD_BASE_URL}"
      ;;
    local)
      [[ -n "${AVATAR_LOCAL_BASE_URL:-}" ]] || fail "AVATAR_MODE=local but AVATAR_LOCAL_BASE_URL is empty"
      echo "local|${AVATAR_LOCAL_BASE_URL}"
      ;;
    auto)
      if [[ -n "${AVATAR_RUNPOD_BASE_URL:-}" ]]; then
        echo "auto-runpod|${AVATAR_RUNPOD_BASE_URL}"
      elif [[ -n "${AVATAR_LOCAL_BASE_URL:-}" ]]; then
        echo "auto-local|${AVATAR_LOCAL_BASE_URL}"
      else
        fail "AVATAR_MODE=auto but neither AVATAR_RUNPOD_BASE_URL nor AVATAR_LOCAL_BASE_URL is set"
      fi
      ;;
    *)
      fail "Unsupported AVATAR_MODE='${AVATAR_MODE:-}'"
      ;;
  esac
}

info "MirrorMind v1 dev startup"
info "Project root: $ROOT_DIR"

require_command docker
require_file "$ENV_FILE"
require_file "$COMPOSE_FILE"

docker compose version >/dev/null 2>&1 || fail "Docker Compose plugin is not available"

# shellcheck disable=SC1090
set -a
source "$ENV_FILE"
set +a

STREAM_MODE_VALUE="${STREAM_MODE:-mock}"
VLLM_BASE_URL_VALUE="${VLLM_BASE_URL:-}"
RESOLVED="$(resolve_avatar_target)"
RESOLUTION_SOURCE="${RESOLVED%%|*}"
RESOLVED_AVATAR_URL="${RESOLVED#*|}"
RESOLVED_AVATAR_URL="$(trim_trailing_slash "$RESOLVED_AVATAR_URL")"
validate_url_like "Resolved avatar URL" "$RESOLVED_AVATAR_URL"

info "STREAM_MODE=$STREAM_MODE_VALUE"
info "Avatar resolution source: $RESOLUTION_SOURCE"
info "Resolved avatar URL: $RESOLVED_AVATAR_URL"

START_LOCAL_AVATAR="false"

case "$RESOLUTION_SOURCE" in
  local|auto-local)
    START_LOCAL_AVATAR="true"
    ;;
  runpod|auto-runpod)
    START_LOCAL_AVATAR="false"
    ;;
  override)
    if [[ "$RESOLVED_AVATAR_URL" =~ ^http://avatar(:[0-9]+)?$ ]] || [[ "$RESOLVED_AVATAR_URL" =~ ^http://localhost(:[0-9]+)?$ ]]; then
      warn "AVATAR_BASE_URL override points local"
      START_LOCAL_AVATAR="true"
    else
      warn "AVATAR_BASE_URL override points remote"
      START_LOCAL_AVATAR="false"
    fi
    ;;
  *)
    fail "Unexpected avatar resolution source: $RESOLUTION_SOURCE"
    ;;
esac

if [[ -n "$VLLM_BASE_URL_VALUE" ]]; then
  info "VLLM_BASE_URL=$VLLM_BASE_URL_VALUE"

  if [[ "$VLLM_BASE_URL_VALUE" =~ ^http://localhost: ]]; then
    warn "VLLM_BASE_URL uses localhost. Inside Docker that usually points to the API container, not vLLM."
    warn "For this compose file, use: http://vllm:8001"
  fi

  if [[ "$VLLM_BASE_URL_VALUE" == "http://vllm:8001" ]]; then
    if [[ "$STREAM_MODE_VALUE" == "mock" ]]; then
      warn "STREAM_MODE=mock, so vLLM is probably not needed right now."
    else
      warn "VLLM_BASE_URL points to the vllm compose service."
      warn "That service is under the 'gpu' profile, so you must start compose with --profile gpu if you want live model inference."
    fi
  fi
fi

if [[ "$START_LOCAL_AVATAR" == "true" ]]; then
  info "Starting services: frontend api tts avatar"
  docker compose -f "$COMPOSE_FILE" up -d frontend api tts avatar
else
  info "Starting services: frontend api tts"
  docker compose -f "$COMPOSE_FILE" up -d frontend api tts
fi

echo
info "Startup complete."
info "Recommended next commands:"
echo "  bash scripts/warmup.sh"
echo "  curl -s http://localhost:8000/health | jq"

if [[ "$START_LOCAL_AVATAR" == "false" ]]; then
  echo "  bash scripts/check_runpod.sh"
fi

if [[ "$STREAM_MODE_VALUE" != "mock" && "$VLLM_BASE_URL_VALUE" == "http://vllm:8001" ]]; then
  echo
  warn "If you need vLLM, start it with:"
  echo "  docker compose -f docker/docker-compose.yml --profile gpu up -d vllm"
fi
