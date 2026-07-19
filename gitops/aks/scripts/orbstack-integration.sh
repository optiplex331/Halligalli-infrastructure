#!/usr/bin/env sh
# Proves the paired runtime against an OrbStack one-node Kubernetes cluster only.
set -eu

usage() {
  cat <<'EOF'
Usage: orbstack-integration.sh [preflight|run]

preflight (default) checks local prerequisites and lints both closed Charts.
run creates disposable resources in an OrbStack cluster after explicit approval.

Environment:
  HALLIGALLI_ORBSTACK_VALUES   Isolated digest-pinned paired-release values JSON.
                                Defaults to the checked-in placeholder for preflight only.
  HALLIGALLI_ORBSTACK_HOST     Local ingress host (default: halligalli.orb.local).
  HALLIGALLI_ORBSTACK_EVIDENCE Output evidence JSON (default: a temporary path).
  HALLIGALLI_ORBSTACK_APPROVED Must equal 1 before run can mutate Kubernetes.

This one-node helper does not prove multi-node scheduling, pod disruption, AKS
networking, cloud DNS/TLS, Argo CD reconciliation, or Azure cost and teardown.
EOF
}

mode="${1:-preflight}"
case "$mode" in
  preflight|run) ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

script_dir="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
gitops_root="$(CDPATH='' cd -- "$script_dir/.." && pwd)"
repo_root="$(CDPATH='' cd -- "$gitops_root/../.." && pwd)"
chart_path="$gitops_root/chart/halligalli"
observability_chart_path="$gitops_root/chart/halligalli-observability"
default_values="$gitops_root/values/halligalli.values.json"
observability_values="$gitops_root/values/halligalli-observability.values.json"
values_path="${HALLIGALLI_ORBSTACK_VALUES:-$default_values}"
host="${HALLIGALLI_ORBSTACK_HOST:-halligalli.orb.local}"
namespace="halligalli"
observability_namespace="halligalli-observability"
tls_secret="halligalli-orbstack-tls"

if [ "$mode" = "run" ] && [ -z "${HALLIGALLI_ORBSTACK_VALUES:-}" ]; then
  echo "OrbStack run requires an explicit HALLIGALLI_ORBSTACK_VALUES file." >&2
  exit 1
fi

for command in docker kubectl helm openssl python3; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "OrbStack preflight requires $command in PATH; do not install it from this helper." >&2
    exit 1
  }
done

if ! docker info --format '{{.OperatingSystem}}' 2>/dev/null | grep -qi 'orbstack'; then
  echo "This helper only targets the local OrbStack Docker engine." >&2
  exit 1
fi

context="$(kubectl config current-context)"
case "$context" in
  *orbstack*) ;;
  *)
    echo "Refusing Kubernetes context '$context'; select an OrbStack context first." >&2
    exit 1
    ;;
esac

[ -f "$values_path" ] || { echo "Missing HALLIGALLI_ORBSTACK_VALUES: $values_path" >&2; exit 1; }

# Lint before any mutation. Chart schemas own the closed values contracts.
helm lint "$chart_path" --values "$values_path" \
  --set "ingress.host=$host" --set "ingress.tlsSecretName=$tls_secret" >/dev/null
helm lint "$observability_chart_path" \
  --values "$observability_values" >/dev/null

redis_secret="$(python3 - "$values_path" <<'PY'
import json
import sys
from pathlib import Path

values = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(values["redisSecretName"])
PY
)"

if [ "$mode" = "preflight" ]; then
  printf '%s\n' "OrbStack preflight passed: both closed Chart schemas passed."
  printf '%s\n' "No Kubernetes, Azure, DNS, or registry operation was performed."
  exit 0
fi

if [ "${HALLIGALLI_ORBSTACK_APPROVED:-}" != "1" ]; then
  echo "Refusing local Kubernetes mutation without HALLIGALLI_ORBSTACK_APPROVED=1." >&2
  exit 1
fi

kubectl cluster-info >/dev/null
kubectl get ingressclass nginx >/dev/null

work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT HUP INT TERM
certificate="$work_dir/tls.crt"
private_key="$work_dir/tls.key"
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj "/CN=$host" \
  -keyout "$private_key" -out "$certificate" >/dev/null 2>&1

kubectl create namespace "$namespace" --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace "$observability_namespace" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "$namespace" create secret generic "$redis_secret" \
  --from-literal=username=halligalli-api --from-literal=password="$(openssl rand -hex 32)" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "$namespace" create secret tls "$tls_secret" --cert="$certificate" --key="$private_key" \
  --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install halligalli-orbstack "$chart_path" --namespace "$namespace" --create-namespace \
  --values "$values_path" --set "ingress.host=$host" --set "ingress.tlsSecretName=$tls_secret"
helm upgrade --install halligalli-orbstack-observability "$observability_chart_path" \
  --namespace "$observability_namespace" --create-namespace --values "$observability_values"

for deployment in halligalli-web halligalli-api halligalli-redis; do
  kubectl -n "$namespace" rollout status "deployment/$deployment" --timeout=180s
done
python3 "$repo_root/.github/utils/verify_running_pod_digests.py" \
  --values "$values_path" --namespace "$namespace" --rollout-timeout 180s
for deployment in prometheus collector tempo; do
  kubectl -n "$observability_namespace" rollout status "deployment/halligalli-observability-$deployment" --timeout=180s
done

kubectl -n "$namespace" get ingress halligalli >/dev/null
kubectl -n "$namespace" get secret "$redis_secret" "$tls_secret" >/dev/null
kubectl -n "$namespace" get networkpolicy halligalli-default-deny halligalli-web halligalli-api halligalli-redis >/dev/null
kubectl -n "$observability_namespace" get networkpolicy halligalli-observability-default-deny halligalli-observability-prometheus-flow halligalli-observability-collector-flow halligalli-observability-tempo-flow >/dev/null
kubectl -n "$observability_namespace" get endpoints halligalli-observability-prometheus halligalli-observability-collector halligalli-observability-tempo >/dev/null
kubectl get --raw "/api/v1/namespaces/$observability_namespace/services/http:halligalli-observability-prometheus:9090/proxy/api/v1/query?query=up" >/dev/null
kubectl get --raw "/api/v1/namespaces/$observability_namespace/services/http:halligalli-observability-tempo:3200/proxy/api/status/buildinfo" >/dev/null
curl --fail --silent --show-error --insecure --resolve "$host:443:127.0.0.1" "https://$host/" >/dev/null

evidence_path="${HALLIGALLI_ORBSTACK_EVIDENCE:-$repo_root/.local/orbstack-one-node-evidence.json}"
mkdir -p "$(dirname -- "$evidence_path")"
python3 - "$evidence_path" "$context" "$host" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

Path(sys.argv[1]).write_text(json.dumps({
    "environment": "OrbStack one-node Kubernetes",
    "recordedAt": datetime.now(timezone.utc).isoformat(),
    "context": sys.argv[2],
    "sameOriginHost": sys.argv[3],
    "validated": ["paired runtime readiness", "selected Web/API Pod digests", "generated Secrets", "Ingress", "NetworkPolicies", "Prometheus query API", "OpenTelemetry Collector readiness", "Tempo query API"],
    "notProven": ["multi-node scheduling", "pod disruption", "AKS networking", "cloud DNS/TLS", "Argo CD reconciliation", "Azure cost and teardown"],
}, indent=2) + "\n", encoding="utf-8")
PY
printf '%s\n' "OrbStack one-node integration passed. Evidence: $evidence_path"
