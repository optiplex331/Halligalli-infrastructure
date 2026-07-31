#!/usr/bin/env bash
set -euo pipefail

die() {
  echo "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage: targets/k3s/scripts/k3s-operator.sh <command>

Commands:
  sync-kubeconfig  Copy the remote admin kubeconfig to local ignored state.
  port-forward     Keep the Kubernetes API reachable through SSH only.
  preflight        Record a read-only cluster and host compatibility report.
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../.." && pwd)"
operation_config="$repo_root/targets/k3s/operator.env"
state_dir="${HALLIGALLI_K3S_STATE_DIR:-$repo_root/.local/k3s}"
kubeconfig_path="$state_dir/admin.kubeconfig"

load_config() {
  [[ -f "$operation_config" ]] || die "Copy targets/k3s/operator.env.example to the ignored targets/k3s/operator.env and fill it locally."

  # shellcheck disable=SC1090
  source "$operation_config"

  : "${HALLIGALLI_K3S_SSH_TARGET:?Set HALLIGALLI_K3S_SSH_TARGET in targets/k3s/operator.env.}"
  : "${HALLIGALLI_K3S_REMOTE_KUBECONFIG:?Set HALLIGALLI_K3S_REMOTE_KUBECONFIG in targets/k3s/operator.env.}"
  : "${HALLIGALLI_K3S_LOCAL_API_PORT:?Set HALLIGALLI_K3S_LOCAL_API_PORT in targets/k3s/operator.env.}"
  : "${HALLIGALLI_K3S_CONTEXT:?Set HALLIGALLI_K3S_CONTEXT in targets/k3s/operator.env.}"

  [[ "$HALLIGALLI_K3S_LOCAL_API_PORT" =~ ^[0-9]+$ ]] ||
    die "HALLIGALLI_K3S_LOCAL_API_PORT must be a numeric local port."
}

load_preflight_config() {
  : "${HALLIGALLI_K3S_REMOTE_DATA_PATH:?Set HALLIGALLI_K3S_REMOTE_DATA_PATH in targets/k3s/operator.env.}"
  : "${HALLIGALLI_K3S_LLM_NAMESPACES:?Set HALLIGALLI_K3S_LLM_NAMESPACES in targets/k3s/operator.env.}"
  : "${HALLIGALLI_K3S_PUBLIC_ORIGIN:?Set HALLIGALLI_K3S_PUBLIC_ORIGIN in targets/k3s/operator.env.}"

  [[ "$HALLIGALLI_K3S_PUBLIC_ORIGIN" == https://* ]] ||
    die "HALLIGALLI_K3S_PUBLIC_ORIGIN must use https://."
  [[ "$HALLIGALLI_K3S_PUBLIC_ORIGIN" != *":6443"* ]] ||
    die "The public origin must not route to Kubernetes API port 6443."
  [[ -n "$HALLIGALLI_K3S_LLM_NAMESPACES" ]] ||
    die "List the protected LLM namespaces in HALLIGALLI_K3S_LLM_NAMESPACES."
}

require_commands() {
  local command_name
  for command_name in "$@"; do
    command -v "$command_name" >/dev/null 2>&1 || die "Required command not found: $command_name"
  done
}

kube() {
  KUBECONFIG="$kubeconfig_path" kubectl --context "$HALLIGALLI_K3S_CONTEXT" "$@"
}

sync_kubeconfig() {
  require_commands kubectl mktemp sed ssh
  mkdir -p "$state_dir"
  chmod 700 "$state_dir"

  local raw_config normalized_config current_context
  raw_config="$(mktemp "$state_dir/admin.kubeconfig.XXXXXX")"
  normalized_config="$(mktemp "$state_dir/admin.kubeconfig.normalized.XXXXXX")"
  cleanup_sync() {
    rm -f -- "$raw_config" "$normalized_config"
  }
  trap cleanup_sync EXIT

  ssh "$HALLIGALLI_K3S_SSH_TARGET" \
    cat -- "$HALLIGALLI_K3S_REMOTE_KUBECONFIG" > "$raw_config"
  sed -E \
    "s#https://[^[:space:]]+:6443#https://127.0.0.1:${HALLIGALLI_K3S_LOCAL_API_PORT}#g" \
    "$raw_config" > "$normalized_config"

  grep -Eq "^[[:space:]]*server:[[:space:]]*https://[^[:space:]]+:6443([[:space:]]*)$" \
    "$normalized_config" && die "The copied kubeconfig still points to remote API port 6443."

  chmod 600 "$normalized_config"
  mv -f "$normalized_config" "$kubeconfig_path"
  current_context="$(KUBECONFIG="$kubeconfig_path" kubectl config current-context)"
  if [[ "$current_context" != "$HALLIGALLI_K3S_CONTEXT" ]]; then
    KUBECONFIG="$kubeconfig_path" kubectl config rename-context \
      "$current_context" "$HALLIGALLI_K3S_CONTEXT" >/dev/null
  fi

  trap - EXIT
  rm -f -- "$raw_config"
  echo "Synchronized local admin context at $kubeconfig_path."
  echo "The kubeconfig remains local-only; it was not printed."
}

port_forward() {
  require_commands ssh
  mkdir -p "$state_dir"
  chmod 700 "$state_dir"
  exec ssh -N -T \
    -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -L "127.0.0.1:${HALLIGALLI_K3S_LOCAL_API_PORT}:127.0.0.1:6443" \
    "$HALLIGALLI_K3S_SSH_TARGET"
}

preflight() {
  require_commands kubectl ssh
  [[ -f "$kubeconfig_path" ]] ||
    die "Run sync-kubeconfig before preflight."
  load_preflight_config

  local report timestamp argocd_namespace namespace
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  report="$state_dir/preflight-$timestamp.txt"
  mkdir -p "$state_dir"
  chmod 700 "$state_dir"

  argocd_namespace="$(kube get namespace argocd --ignore-not-found -o name)"

  {
    echo "Halligalli K3s read-only preflight"
    echo "Generated at: $timestamp"
    echo "SSH target: $HALLIGALLI_K3S_SSH_TARGET"
    echo "Kubernetes API: https://127.0.0.1:$HALLIGALLI_K3S_LOCAL_API_PORT via SSH port-forward"
    echo "Local context: $HALLIGALLI_K3S_CONTEXT"
    echo "Public origin: $HALLIGALLI_K3S_PUBLIC_ORIGIN"
    echo "Public route check: passed; the configured public origin does not select port 6443."
    echo

    echo "== Kubernetes version =="
    kube version --output=yaml
    echo

    echo "== Node capacity and status =="
    kube get nodes -o 'custom-columns=NAME:.metadata.name,READY:.status.conditions[?(@.type=="Ready")].status,CPU:.status.capacity.cpu,MEMORY:.status.capacity.memory,EPHEMERAL_STORAGE:.status.capacity.ephemeral-storage'
    echo

    echo "== Existing Argo CD =="
    if [[ -n "$argocd_namespace" ]]; then
      kube -n argocd get pods,deployments,statefulsets,services -o wide
    else
      echo "namespace/argocd not found"
    fi
    echo

    echo "== Protected K3s add-ons in kube-system =="
    kube -n kube-system get pods,daemonsets,deployments,statefulsets,services -o wide --ignore-not-found
    echo

    echo "== Protected LLM namespaces =="
    IFS=',' read -r -a llm_namespaces <<< "$HALLIGALLI_K3S_LLM_NAMESPACES"
    for namespace in "${llm_namespaces[@]}"; do
      namespace="$(printf '%s' "$namespace" | tr -d '[:space:]')"
      [[ -n "$namespace" ]] || continue
      echo "-- $namespace --"
      kube get namespace "$namespace" -o name
      kube -n "$namespace" get pods,deployments,statefulsets,daemonsets,services -o wide
    done
    echo

    echo "== Host disk at K3s data path =="
    ssh "$HALLIGALLI_K3S_SSH_TARGET" \
      df -hP -- "$HALLIGALLI_K3S_REMOTE_DATA_PATH"
    echo

    echo "== Safety boundary =="
    echo "This report used read-only kubectl and SSH access."
    echo "Shared K3s add-ons and protected LLM namespaces are external state."
    echo "No apply, upgrade, delete, restart, or other mutation was requested."
  } > "$report"

  echo "K3s read-only preflight passed; review $report."
  echo "The report and kubeconfig remain under ignored local state."
}

[[ $# -eq 1 ]] || {
  usage >&2
  exit 2
}

case "$1" in
  -h|--help)
    usage
    ;;
  sync-kubeconfig)
    load_config
    sync_kubeconfig
    ;;
  port-forward)
    load_config
    port_forward
    ;;
  preflight)
    load_config
    preflight
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
