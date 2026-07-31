#!/usr/bin/env bash
set -euo pipefail

die() {
  echo "$*" >&2
  exit 1
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../.." && pwd)"
operation_config="$repo_root/targets/k3s/operator.env"
[[ -f "$operation_config" ]] || die "Copy targets/k3s/operator.env.example to targets/k3s/operator.env first."

# shellcheck disable=SC1090
source "$operation_config"
: "${HALLIGALLI_K3S_CONTEXT:?Set HALLIGALLI_K3S_CONTEXT in targets/k3s/operator.env.}"

state_dir="${HALLIGALLI_K3S_STATE_DIR:-$repo_root/.local/k3s}"
kubeconfig_path="$state_dir/admin.kubeconfig"
web_port=18080
api_port=18000
[[ -f "$kubeconfig_path" ]] || die "Run k3s-operator.sh sync-kubeconfig first."

command -v curl >/dev/null 2>&1 || die "Required command not found: curl"
command -v kubectl >/dev/null 2>&1 || die "Required command not found: kubectl"

kube() {
  KUBECONFIG="$kubeconfig_path" kubectl --context "$HALLIGALLI_K3S_CONTEXT" "$@"
}

smoke_dir="$state_dir/smoke"
mkdir -p "$smoke_dir"
web_log="$smoke_dir/web-port-forward.log"
api_log="$smoke_dir/api-port-forward.log"

cleanup() {
  kill "${web_pid:-}" "${api_pid:-}" 2>/dev/null || true
  wait "${web_pid:-}" "${api_pid:-}" 2>/dev/null || true
}
trap cleanup EXIT

kube -n halligalli port-forward service/halligalli-web "$web_port:80" > "$web_log" 2>&1 &
web_pid=$!
kube -n halligalli port-forward service/halligalli-api "$api_port:80" > "$api_log" 2>&1 &
api_pid=$!

wait_for() {
  local url=$1
  local attempt
  for ((attempt = 1; attempt <= 30; attempt++)); do
    if curl --fail --silent --show-error "$url" >/dev/null; then
      return
    fi
    sleep 1
  done
  die "Timed out waiting for $url"
}

wait_for "http://127.0.0.1:$web_port/"
wait_for "http://127.0.0.1:$api_port/internal/ready"
curl --fail --silent --show-error "http://127.0.0.1:$web_port/internal/identity" >/dev/null
curl --fail --silent --show-error "http://127.0.0.1:$api_port/internal/metrics" | grep -q 'halligalli_http_requests_total'

response="$(curl --fail --silent --show-error \
  -X POST "http://127.0.0.1:$web_port/api/v1/rooms" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: 00000000-0000-4000-8000-000000000002' \
  -d '{"name":"K3s smoke","credentialVerifier":"0000000000000000000000000000000000000000000000000000000000000000","tableSeatCount":4,"targetHumanParticipantCount":2,"difficulty":"normal","durationSec":60}')"
[[ "$response" == *'"roomCode"'* ]] || die "The Web/API/Redis smoke did not create a room."

echo "K3s internal runtime smoke passed for Web, API, and ephemeral Redis."
