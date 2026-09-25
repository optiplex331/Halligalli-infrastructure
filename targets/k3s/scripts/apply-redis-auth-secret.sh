#!/usr/bin/env bash
set -euo pipefail

die() {
  echo "$*" >&2
  exit 1
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../.." && pwd)"
operator_config="$repo_root/targets/k3s/operator.env"

[[ -f "$operator_config" ]] || die "Copy targets/k3s/operator.env.example to operator.env first."

# shellcheck disable=SC1090
source "$operator_config"
: "${HALLIGALLI_K3S_CONTEXT:?Set HALLIGALLI_K3S_CONTEXT in targets/k3s/operator.env.}"
context="$HALLIGALLI_K3S_CONTEXT"

[[ "${HALLIGALLI_OPERATION_APPROVED:-}" == 1 ]] ||
  die "Refusing Kubernetes Secret mutation without HALLIGALLI_OPERATION_APPROVED=1."

if kubectl --context "$context" -n halligalli get secret halligalli-redis-auth >/dev/null 2>&1; then
  echo "The operation-time Redis Secret already exists in halligalli; left unchanged."
  exit 0
fi

password="$(openssl rand -hex 32)"
kubectl --context "$context" \
  -n halligalli create secret generic halligalli-redis-auth \
  --from-literal=username=halligalli-api \
  --from-literal="password=$password" \
  --dry-run=client -o yaml |
  kubectl --context "$context" apply -f -

echo "Applied the operation-time Redis Secret to halligalli."
