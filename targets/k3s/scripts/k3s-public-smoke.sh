#!/usr/bin/env bash
set -euo pipefail

die() {
  echo "$*" >&2
  exit 1
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../.." && pwd)"
origin="${1:-https://k3s.halligalli.games}"

command -v curl >/dev/null 2>&1 || die "Required command not found: curl"
command -v python3 >/dev/null 2>&1 || die "Required command not found: python3"

python3 "$repo_root/.github/utils/external_monitor.py" \
  --origin "$origin" \
  --websocket-path /ws/v1/rooms/k3s-smoke

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
