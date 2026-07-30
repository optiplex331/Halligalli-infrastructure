#!/usr/bin/env bash
# Proves the paired runtime against an OrbStack one-node Kubernetes cluster only.
set -euo pipefail

die() {
  echo "$*" >&2
  exit 1
}

cleanup() {
  [[ -z $work_dir ]] || rm -rf -- "$work_dir"
  kubectl delete namespace "$namespace" --ignore-not-found --wait=true --timeout=180s
}

aks_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
gitops_root="$aks_root/gitops"
repo_root="$(cd "$aks_root/../.." && pwd)"
chart_path="$gitops_root/halligalli"
values_path="${HALLIGALLI_ORBSTACK_VALUES:-}"
host="${HALLIGALLI_ORBSTACK_HOST:-halligalli.orb.local}"
namespace="halligalli"
tls_secret="halligalli-orbstack-tls"
redis_secret="halligalli-redis-auth"
work_dir=""

[[ -f $values_path ]] ||
  die "OrbStack integration requires an existing HALLIGALLI_ORBSTACK_VALUES file: $values_path"

context="$(kubectl config current-context)"
[[ $context == *orbstack* ]] ||
  die "Refusing Kubernetes context '$context'; select an OrbStack context first."

runtime_values=(
  --values "$values_path"
  --set "ingress.host=$host"
  --set "ingress.tlsSecretName=$tls_secret"
  --set "tls.enabled=false"
)

[[ ${HALLIGALLI_ORBSTACK_APPROVED:-} == 1 ]] ||
  die "Refusing local Kubernetes mutation without HALLIGALLI_ORBSTACK_APPROVED=1."

kubectl create namespace "$namespace"
trap cleanup EXIT

work_dir="$(mktemp -d)"
certificate="$work_dir/tls.crt"
private_key="$work_dir/tls.key"
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj "/CN=$host" \
  -keyout "$private_key" -out "$certificate" >/dev/null 2>&1

kubectl -n "$namespace" create secret generic "$redis_secret" \
  --from-literal=username=halligalli-api --from-literal=password="$(openssl rand -hex 32)" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n "$namespace" create secret tls "$tls_secret" --cert="$certificate" --key="$private_key" \
  --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install halligalli-orbstack "$chart_path" --namespace "$namespace" \
  "${runtime_values[@]}"

python3 "$repo_root/.github/utils/verify_running_pod_digests.py" \
  --values "$values_path" --namespace "$namespace" --rollout-timeout 180s

curl --fail --silent --show-error --insecure --resolve "$host:443:127.0.0.1" "https://$host/" >/dev/null

echo "OrbStack runtime smoke passed; disposable namespace will now be deleted."
