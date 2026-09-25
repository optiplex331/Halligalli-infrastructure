#!/usr/bin/env bash
set -euo pipefail

die() {
  echo "$*" >&2
  exit 1
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../.." && pwd)"
operation_config="$repo_root/targets/k3s/operator.env"

load_config() {
  [[ -f "$operation_config" ]] || die "Copy targets/k3s/operator.env.example to targets/k3s/operator.env and fill it locally."

  # shellcheck disable=SC1090
  source "$operation_config"

  : "${HALLIGALLI_K3S_SSH_TARGET:?Set HALLIGALLI_K3S_SSH_TARGET in targets/k3s/operator.env.}"
  : "${HALLIGALLI_K3S_REMOTE_DATA_PATH:?Set HALLIGALLI_K3S_REMOTE_DATA_PATH in targets/k3s/operator.env.}"
  : "${HALLIGALLI_K3S_LLM_NAMESPACES:?Set HALLIGALLI_K3S_LLM_NAMESPACES in targets/k3s/operator.env.}"
  : "${HALLIGALLI_K3S_CONTEXT:?Set HALLIGALLI_K3S_CONTEXT in targets/k3s/operator.env.}"
}

require_commands() {
  local command_name
  for command_name in "$@"; do
    command -v "$command_name" >/dev/null 2>&1 || die "Required command not found: $command_name"
  done
}

kube() {
  kubectl --context "$HALLIGALLI_K3S_CONTEXT" "$@"
}

check_nodes() {
  local node_status ready=0 total=0
  node_status="$(kube get nodes -o jsonpath='{range .items[*]}{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}')"

  while read -r status; do
    [[ -n "$status" ]] || continue
    total=$((total + 1))
    [[ "$status" == True ]] && ready=$((ready + 1))
  done <<< "$node_status"

  [[ $ready -gt 0 ]] || die "No K3s node is Ready."
  echo "Ready nodes: $ready of $total"
}

check_argocd() {
  kube get namespace argocd >/dev/null || die "Required namespace not found: argocd"
  kube get crd applications.argoproj.io appprojects.argoproj.io >/dev/null ||
    die "The shared Argo CD Application and AppProject CRDs are missing."
  kube auth can-i create applications.argoproj.io -n argocd >/dev/null ||
    die "The context cannot create Argo CD Applications in argocd."
  echo "Shared Argo CD: namespace and CRDs exist; Applications can be created."
}

check_namespaces() {
  local namespace
  IFS=',' read -r -a llm_namespaces <<< "$HALLIGALLI_K3S_LLM_NAMESPACES"
  for namespace in "${llm_namespaces[@]}"; do
    namespace="$(printf '%s' "$namespace" | tr -d '[:space:]')"
    [[ -n "$namespace" ]] || continue
    case "$namespace" in
      halligalli|halligalli-observability|halligalli-edge)
        die "Protected LLM namespace overlaps a Halligalli namespace: $namespace"
        ;;
    esac
    kube get namespace "$namespace" >/dev/null ||
      die "Protected LLM namespace not found: $namespace"
  done
  echo "Protected LLM namespaces exist and do not overlap Halligalli namespaces."

  for namespace in halligalli halligalli-observability halligalli-edge; do
    if kube get namespace "$namespace" >/dev/null 2>&1; then
      echo "Halligalli namespace $namespace: exists"
    else
      echo "Halligalli namespace $namespace: not created yet"
    fi
  done
}

[[ $# -eq 0 ]] || die "Usage: targets/k3s/scripts/k3s-preflight.sh"

load_config
require_commands kubectl ssh curl python3 terraform openssl

echo "Halligalli K3s read-only preflight"
echo "== Access =="
"$script_dir/k3s-access.sh" check
echo
echo "== Kubernetes version =="
kube get --raw /version |
  python3 -c 'import json, sys; print("Server: " + json.load(sys.stdin)["gitVersion"])'
echo
echo "== Nodes =="
check_nodes
echo
echo "== Shared Argo CD =="
check_argocd
echo
echo "== Namespaces =="
check_namespaces
echo
echo "== K3s data path disk =="
ssh "$HALLIGALLI_K3S_SSH_TARGET" df -hP -- "$HALLIGALLI_K3S_REMOTE_DATA_PATH" |
  awk 'NR == 2 { print "Available: " $4 " (" $5 " used)" }'
echo
echo "K3s read-only preflight passed."
