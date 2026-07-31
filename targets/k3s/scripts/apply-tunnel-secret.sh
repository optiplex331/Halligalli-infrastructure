#!/usr/bin/env bash
set -euo pipefail

die() {
  echo "$*" >&2
  exit 1
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../.." && pwd)"
operation_config="$repo_root/targets/k3s/terraform/local-operation.env"
operator_config="$repo_root/targets/k3s/operator.env"
terraform_root="$repo_root/targets/k3s/terraform"

[[ -f "$operation_config" ]] || die "Copy targets/k3s/terraform/local-operation.env.example to local-operation.env first."
[[ -f "$operator_config" ]] || die "Copy targets/k3s/operator.env.example to operator.env first."

# shellcheck disable=SC1090
source "$operator_config"
kubeconfig_path="${HALLIGALLI_K3S_STATE_DIR:-$repo_root/.local/k3s}/admin.kubeconfig"
[[ -f "$kubeconfig_path" ]] || die "Run k3s-operator.sh sync-kubeconfig first."

set -a
# shellcheck disable=SC1090
source "$operation_config"
set +a

[[ "${HALLIGALLI_OPERATION_APPROVED:-}" == 1 ]] ||
  die "Refusing Kubernetes Secret mutation without HALLIGALLI_OPERATION_APPROVED=1."

: "${HALLIGALLI_K3S_CONTEXT:?Set HALLIGALLI_K3S_CONTEXT in targets/k3s/operator.env.}"
context="$HALLIGALLI_K3S_CONTEXT"

command -v terraform >/dev/null 2>&1 || die "Required command not found: terraform"
command -v kubectl >/dev/null 2>&1 || die "Required command not found: kubectl"

tunnel_token="$(terraform -chdir="$terraform_root" output -raw tunnel_token)"
[[ -n "$tunnel_token" ]] || die "Terraform did not return a Tunnel token."

export KUBECONFIG="$kubeconfig_path"
kubectl --context "$context" \
  -n halligalli-edge create secret generic halligalli-tunnel \
  --from-literal="token=$tunnel_token" \
  --dry-run=client -o yaml |
  kubectl --context "$context" apply -f -

echo "Applied the operation-time Tunnel Secret to halligalli-edge."
