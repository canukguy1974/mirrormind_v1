#!/usr/bin/env bash
set -euo pipefail

# scripts/check_runpod.sh
# Validates the remote avatar endpoint based on current MirrorMind precedence.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
CURL_BIN="${CURL_BIN:-curl}"

fail() {
  echo "❌ $1" >&2
  exit 1
}

info() {
  echo "==> $1"
}

warn() {
  echo "⚠️  $1"
}

[[ -f "$ENV_FILE" ]] || fail "Missing .env at project root"

# shellcheck disable=SC1090
set -a
source "$ENV_FILE"
set +a

resolve_avatar_target() {
  if [[ -n "${AVATAR_BASE_URL:-}" ]]; then
    echo "override|${AVATAR_BASE_URL}"
    return
  fi

  case "${AVATAR_MODE:-auto}" in
    runpod)
      [[ -n "${AVATAR_RUNPOD_BASE_URL:-}" ]] || fail "AVATAR_MODE=runpod but AVATAR_RUNPOD_BASE_URL is not set"
      echo "runpod|${AVATAR_RUNPOD_BASE_URL}"
      ;;
    auto)
      [[ -n "${AVATAR_RUNPOD_BASE_URL:-}" ]] || fail "No AVATAR_RUNPOD_BASE_URL available for remote check"
      echo "auto-runpod|${AVATAR_RUNPOD_BASE_URL}"
      ;;
    local)
      fail "AVATAR_MODE=local; remote RunPod check is not applicable"
      ;;
    *)
      fail "Unsupported or unknown AVATAR_MODE='${AVATAR_MODE:-}'"
      ;;
  esac
}

RESOLVED="$(resolve_avatar_target)"
RESOLUTION_SOURCE="${RESOLVED%%|*}"
BASE_URL="${RESOLVED#*|}"
BASE_URL="${BASE_URL%/}"

[[ -n "$BASE_URL" ]] || fail "Resolved remote avatar URL is empty"
[[ "$BASE_URL" =~ ^https?:// ]] || fail "Resolved avatar URL must start with http:// or https://"

if [[ "$BASE_URL" =~ ^http://avatar(:[0-9]+)?$ ]] || [[ "$BASE_URL" =~ ^http://localhost(:[0-9]+)?$ ]]; then
  fail "Resolved avatar URL points to a local endpoint, not RunPod: $BASE_URL"
fi

HEALTH_URL="${BASE_URL}/health"
TMP_FILE="$(mktemp)"
trap 'rm -f "$TMP_FILE"' EXIT

info "Avatar resolution source: $RESOLUTION_SOURCE"
info "Checking remote avatar health: $HEALTH_URL"

CURL_OUTPUT="$("$CURL_BIN" -sS -o "$TMP_FILE" -w "%{http_code} %{time_total}" --max-time 20 "$HEALTH_URL" 2>&1)" \
  || fail "Remote request failed: $CURL_OUTPUT"

HTTP_CODE="$(awk '{print $1}' <<<"$CURL_OUTPUT")"
TIME_TOTAL="$(awk '{print $2}' <<<"$CURL_OUTPUT")"

info "HTTP status: $HTTP_CODE"
info "Latency: ${TIME_TOTAL}s"

if [[ ! "$HTTP_CODE" =~ ^2[0-9][0-9]$ ]]; then
  cat "$TMP_FILE" || true
  fail "Remote avatar health returned HTTP $HTTP_CODE"
fi

echo
info "Response body:"
if command -v jq >/dev/null 2>&1; then
  jq . "$TMP_FILE" 2>/dev/null || cat "$TMP_FILE"
else
  cat "$TMP_FILE"
fi

echo
info "Remote avatar endpoint is reachable."
