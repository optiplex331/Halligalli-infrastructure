#!/usr/bin/env bash
set -euo pipefail

die() {
  echo "$*" >&2
  exit 1
}

script_path="${BASH_SOURCE[0]}"
script_dir="$(dirname "$script_path")"
repo_root="$(cd "$script_dir/../../.." && pwd)"
operation_config="$repo_root/targets/aks/terraform/local-operation.env"

[[ -f "$operation_config" ]] ||
  die "Copy targets/aks/terraform/local-operation.env.example to the ignored local-operation.env and fill it locally."

# shellcheck disable=SC1090
source "$operation_config"

[[ "${HALLIGALLI_OPERATION_APPROVED:-}" == 1 ]] ||
  die "Refusing Azure preflight without HALLIGALLI_OPERATION_APPROVED=1 in the local operation configuration."

[[ -n "${AZURE_SUBSCRIPTION_ID:-}" ]] ||
  die "Set AZURE_SUBSCRIPTION_ID in targets/aks/terraform/local-operation.env."

terraform_root="$repo_root/targets/aks/terraform"
backend_config="$terraform_root/backend.hcl"
output_dir="${HALLIGALLI_AKS_PREFLIGHT_OUTPUT:-$repo_root/.local/aks-preflight}"
export ARM_SUBSCRIPTION_ID="$AZURE_SUBSCRIPTION_ID"

[[ -f "$backend_config" ]] ||
  die "Copy targets/aks/terraform/backend.hcl.example to the ignored backend.hcl and fill it locally."

read -r actual_subscription subscription_state < <(
  az account show --subscription "$AZURE_SUBSCRIPTION_ID" --query '[id,state]' -o tsv
)
[[ "$actual_subscription" == "$AZURE_SUBSCRIPTION_ID" ]] ||
  die "The selected Azure subscription does not match AZURE_SUBSCRIPTION_ID."
[[ "$subscription_state" == "Enabled" ]] ||
  die "The selected Azure subscription is not enabled."

mkdir -p "$output_dir"
terraform -chdir="$terraform_root" init \
  -backend-config="$backend_config" -input=false
terraform -chdir="$terraform_root" plan -no-color -input=false \
  -out="$output_dir/create.tfplan" > "$output_dir/create-plan.txt"

echo "AKS technical preflight passed; review $output_dir/create-plan.txt before requesting separate apply approval."
echo "A successful plan is not authorization to apply."
