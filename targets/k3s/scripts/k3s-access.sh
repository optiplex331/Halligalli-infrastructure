#!/usr/bin/env bash
set -euo pipefail

die() {
  echo "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage: targets/k3s/scripts/k3s-access.sh <command>

Commands:
  check         Confirm the operator kubeconfig has the K3s context and that
                it reaches the API only through a loopback address.
  port-forward  Keep the Kubernetes API reachable through SSH only.

The operator's own kubeconfig (KUBECONFIG or ~/.kube/config) supplies the
credentials. This script never copies, writes, or prints kubeconfig contents.
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../.." && pwd)"
operation_config="$repo_root/targets/k3s/operator.env"

load_config() {
  [[ -f "$operation_config" ]] || die "Copy targets/k3s/operator.env.example to the ignored targets/k3s/operator.env and fill it locally."

  # shellcheck disable=SC1090
  source "$operation_config"

  : "${HALLIGALLI_K3S_CONTEXT:?Set HALLIGALLI_K3S_CONTEXT in targets/k3s/operator.env.}"
  : "${HALLIGALLI_K3S_LOCAL_API_PORT:?Set HALLIGALLI_K3S_LOCAL_API_PORT in targets/k3s/operator.env.}"

  [[ "$HALLIGALLI_K3S_LOCAL_API_PORT" =~ ^[0-9]+$ ]] ||
    die "HALLIGALLI_K3S_LOCAL_API_PORT must be a numeric local port."
}

check_context() {
  local server
  kubectl config get-contexts -o name | grep -Fxq -- "$HALLIGALLI_K3S_CONTEXT" ||
    die "Context $HALLIGALLI_K3S_CONTEXT is not in the operator kubeconfig."

  server="$(kubectl config view --minify --context "$HALLIGALLI_K3S_CONTEXT" \
    -o jsonpath='{.clusters[0].cluster.server}')"
  [[ "$server" =~ ^https://(127\.0\.0\.1|localhost|\[::1\]):[0-9]+/?$ ]] ||
    die "Context $HALLIGALLI_K3S_CONTEXT must use a loopback API server, not $server."

  echo "Context $HALLIGALLI_K3S_CONTEXT uses loopback API server $server."
}

port_forward() {
  : "${HALLIGALLI_K3S_SSH_TARGET:?Set HALLIGALLI_K3S_SSH_TARGET in targets/k3s/operator.env.}"
  exec ssh -N -T \
    -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -L "127.0.0.1:${HALLIGALLI_K3S_LOCAL_API_PORT}:127.0.0.1:6443" \
    "$HALLIGALLI_K3S_SSH_TARGET"
}

[[ $# -eq 1 ]] || {
  usage >&2
  exit 2
}

case "$1" in
  -h|--help)
    usage
    ;;
  check)
    load_config
    check_context
    ;;
  port-forward)
    load_config
    port_forward
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
