#!/usr/bin/env bash
set -euo pipefail

die() {
  echo "$*" >&2
  exit 1
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../.." && pwd)"
origin="${1:-https://k3s.halligalli.games}"

python3 "$repo_root/.github/utils/external_monitor.py" \
  --origin "$origin" \
  --websocket-path /ws/v1/rooms/k3s-smoke \
  --desired-state "$repo_root/targets/k3s/gitops/runtime/values/experiment.values.json" \
  --wait-seconds 300

rest_status="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
  --request POST \
  --header 'Content-Type: application/json' \
  --header 'Idempotency-Key: 00000000-0000-4000-8000-000000000003' \
  --data '{}' \
  "$origin/api/v1/rooms")"
if [[ "$rest_status" != 422 && "$rest_status" != 401 ]]; then
  die "Public REST route returned unexpected status: $rest_status"
fi

echo "K3s public HTTPS, REST, and WebSocket smoke passed."
