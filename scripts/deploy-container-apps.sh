#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
desired_state="${1:-${repo_root}/deployment/container-apps/desired-state.json}"
resource_group="halligalli-container-apps"
container_app="halligalli-live-demo"
candidate_dir="$(mktemp -d)"
candidate_file="${candidate_dir}/candidate-revision.json"
candidate_identity="${candidate_dir}/candidate-identity.json"
candidate_revision=""
previous_revision=""

cleanup() {
  exit_code=$?
  if ((exit_code != 0)) && [[ -n "${previous_revision}" ]]; then
    if ! az containerapp ingress traffic set \
      --resource-group "${resource_group}" \
      --name "${container_app}" \
      --revision-weight "${previous_revision}=100" >/dev/null; then
      printf 'Deployment failed and automatic traffic restoration also failed.\n' >&2
    fi
    if [[ -n "${candidate_revision}" ]]; then
      if ! az containerapp revision deactivate \
        --resource-group "${resource_group}" \
        --name "${container_app}" \
        --revision "${candidate_revision}" >/dev/null; then
        printf 'Candidate revision could not be deactivated: %s\n' "${candidate_revision}" >&2
      fi
    fi
    printf 'Deployment failed; traffic was restored to %s.\n' "${previous_revision}" >&2
  fi
  rm -rf "${candidate_dir}"
  exit "${exit_code}"
}
trap cleanup EXIT

for command_name in az curl python3; do
  command -v "${command_name}" >/dev/null || {
    printf 'Required command is unavailable: %s\n' "${command_name}" >&2
    exit 1
  }
done

az account show >/dev/null 2>&1 || {
  printf 'No interactive Azure CLI session. Run az login, select the target subscription, and retry.\n' >&2
  exit 1
}

az group show --name "${resource_group}" >/dev/null
az containerapp show --resource-group "${resource_group}" --name "${container_app}" >/dev/null

release_commit="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["releaseCommit"])' "${desired_state}")"
revision_suffix="r$(date -u +%s)-${release_commit:0:7}"
candidate_revision="${container_app}--${revision_suffix}"

python3 "${repo_root}/.github/utils/container_apps_revision.py" \
  "${desired_state}" \
  --revision-suffix "${revision_suffix}" \
  --output "${candidate_file}"

# shellcheck disable=SC2016
previous_revision="$(az containerapp ingress traffic show \
  --resource-group "${resource_group}" \
  --name "${container_app}" \
  --query '[?weight==`100`].revisionName | [0]' \
  --output tsv)"
test -n "${previous_revision}"

az containerapp update \
  --resource-group "${resource_group}" \
  --name "${container_app}" \
  --yaml "${candidate_file}" >/dev/null

candidate_fqdn="$(az containerapp revision show \
  --resource-group "${resource_group}" \
  --name "${container_app}" \
  --revision "${candidate_revision}" \
  --query properties.fqdn \
  --output tsv)"
test -n "${candidate_fqdn}"
candidate_origin="https://${candidate_fqdn}"

curl --fail --silent "${candidate_origin}/internal/identity" >"${candidate_identity}"
python3 "${repo_root}/.github/utils/external_monitor.py" \
  --origin "${candidate_origin}" \
  --websocket-path /ws/v1/rooms/monitor
python3 - "${desired_state}" "${candidate_identity}" <<'PY'
import json
import sys

state = json.load(open(sys.argv[1], encoding="utf-8"))
identity = json.load(open(sys.argv[2], encoding="utf-8"))
assert identity == {
    "version": state["releaseVersion"],
    "commit": state["releaseCommit"],
}
PY

az containerapp ingress traffic set \
  --resource-group "${resource_group}" \
  --name "${container_app}" \
  --revision-weight "${candidate_revision}=100" >/dev/null
printf 'Deployed %s and switched 100%% traffic from %s.\n' \
  "${candidate_revision}" "${previous_revision}"
