#!/usr/bin/env bash
set -u

# scripts/warmup.sh
# Warmup helper based on current MirrorMind avatar precedence.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
API_HEALTH_URL="${API_HEALTH_URL:-http://localhost:8000/health}"
CURL_BIN="${CURL_BIN:-curl}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a
  source "$ENV_FILE"
  set +a
fi

timestamp() {
  date +"%Y-%m-%d %H:%M:%S"
}

info() {
  echo "[$(timestamp)] ==> $1"
}

warn() {
  echo "[$(timestamp)] ⚠️  $1"
}

resolve_avatar_target() {
  if [[ -n "${AVATAR_BASE_URL:-}" ]]; then
    echo "override|${AVATAR_BASE_URL}"
    return
  fi

  case "${AVATAR_MODE:-auto}" in
    runpod)
      [[ -n "${AVATAR_RUNPOD_BASE_URL:-}" ]] && echo "runpod|${AVATAR_RUNPOD_BASE_URL}" || echo "runpod|"
      ;;
    local)
      [[ -n "${AVATAR_LOCAL_BASE_URL:-}" ]] && echo "local|${AVATAR_LOCAL_BASE_URL}" || echo "local|"
      ;;
    auto)
      if [[ -n "${AVATAR_RUNPOD_BASE_URL:-}" ]]; then
        echo "auto-runpod|${AVATAR_RUNPOD_BASE_URL}"
      else
        echo "auto-local|${AVATAR_LOCAL_BASE_URL:-}"
      fi
      ;;
    *)
      echo "unknown|"
      ;;
  esac
}

check_url() {
  local label="$1"
  local url="$2"

  local tmp_file
  tmp_file="$(mktemp)"

  local curl_output
  if curl_output="$("$CURL_BIN" -sS -o "$tmp_file" -w "%{http_code} %{time_total}" --max-time 15 "$url" 2>&1)"; then
    local http_code time_total
    http_code="$(awk '{print $1}' <<<"$curl_output")"
    time_total="$(awk '{print $2}' <<<"$curl_output")"

    if [[ "$http_code" =~ ^2[0-9][0-9]$ ]]; then
      info "$label OK (HTTP $http_code, ${time_total}s)"
      if command -v jq >/dev/null 2>&1; then
        jq . "$tmp_file" 2>/dev/null || cat "$tmp_file"
      else
        cat "$tmp_file"
      fi
    else
      warn "$label returned HTTP $http_code (${time_total}s)"
      cat "$tmp_file"
    fi
  else
    warn "$label request failed: $curl_output"
  fi

  rm -f "$tmp_file"
}

echo "============================================================"
echo "MirrorMind warmup"
echo "============================================================"

info "Checking API health"
check_url "API health" "$API_HEALTH_URL"

RESOLVED="$(resolve_avatar_target)"
RESOLUTION_SOURCE="${RESOLVED%%|*}"
RESOLVED_AVATAR_URL="${RESOLVED#*|}"
RESOLVED_AVATAR_URL="${RESOLVED_AVATAR_URL%/}"

info "Avatar resolution source: $RESOLUTION_SOURCE"

if [[ "$RESOLUTION_SOURCE" == "local" || "$RESOLUTION_SOURCE" == "auto-local" ]]; then
  if [[ -n "$RESOLVED_AVATAR_URL" ]]; then
    info "Checking local avatar health"
    check_url "Local avatar health" "${RESOLVED_AVATAR_URL}/health"
  else
    warn "Resolved local avatar URL is empty"
  fi
elif [[ "$RESOLUTION_SOURCE" == "override" ]]; then
  if [[ "$RESOLVED_AVATAR_URL" =~ ^http://avatar(:[0-9]+)?$ ]] || [[ "$RESOLVED_AVATAR_URL" =~ ^http://localhost(:[0-9]+)?$ ]]; then
    info "Override points local, checking avatar health"
    check_url "Override avatar health" "${RESOLVED_AVATAR_URL}/health"
  else
    info "Override points remote, skipping here. Use scripts/check_runpod.sh"
  fi
else
  info "Remote avatar path detected, skipping here. Use scripts/check_runpod.sh"
fi

info "Warmup complete"
exit 0
