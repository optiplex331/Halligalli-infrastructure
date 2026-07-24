#!/usr/bin/env sh
# Performs no cloud mutations. Terraform plan may acquire a remote state lock.
set -eu

repo_root="$(CDPATH='' cd -- "$(dirname -- "$0")/../../.." && pwd)"
operation_config="$repo_root/targets/aks/terraform/local-operation.env"

[ -f "$operation_config" ] || {
  echo "Copy targets/aks/terraform/local-operation.env.example to the ignored local-operation.env and fill it locally." >&2
  exit 1
}

# shellcheck disable=SC1090
. "$operation_config"

[ "${HALLIGALLI_OPERATION_APPROVED:-}" = "1" ] || {
  echo "Refusing Azure preflight without HALLIGALLI_OPERATION_APPROVED=1 in the local operation configuration." >&2
  exit 1
}

[ -n "${AZURE_SUBSCRIPTION_ID:-}" ] || {
  echo "Set AZURE_SUBSCRIPTION_ID in targets/aks/terraform/local-operation.env." >&2
  exit 1
}
[ -n "${HCP_TERRAFORM_ORGANIZATION:-}" ] || {
  echo "Set HCP_TERRAFORM_ORGANIZATION in targets/aks/terraform/local-operation.env." >&2
  exit 1
}
[ -n "${HCP_TERRAFORM_WORKSPACE:-}" ] || {
  echo "Set HCP_TERRAFORM_WORKSPACE in targets/aks/terraform/local-operation.env." >&2
  exit 1
}

for command in az terraform python3; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "AKS preflight requires $command in PATH; do not install it from this helper." >&2
    exit 1
  }
done

terraform_root="$repo_root/targets/aks/terraform"
target_facts="$terraform_root/target.json"
output_dir="${HALLIGALLI_AKS_PREFLIGHT_OUTPUT:-$repo_root/.local/aks-preflight}"
region="$(python3 "$repo_root/.github/utils/validate_aks_preflight.py" target-field \
  --target-facts "$target_facts" --name region)"
export ARM_SUBSCRIPTION_ID="$AZURE_SUBSCRIPTION_ID"

mkdir -p "$output_dir"
az account show --subscription "$AZURE_SUBSCRIPTION_ID" \
  --query '{id:id,name:name,tenantId:tenantId,state:state}' -o json \
  > "$output_dir/subscription.json"
az rest --method get \
  --url "https://management.azure.com/subscriptions/$AZURE_SUBSCRIPTION_ID/providers/Microsoft.Compute/skus?api-version=2021-07-01&%24filter=location%20eq%20%27$region%27" \
  -o json > "$output_dir/resource-skus.json"
az vm list-usage --subscription "$AZURE_SUBSCRIPTION_ID" \
  --location "$region" -o json > "$output_dir/quota.json"
az aks get-versions --subscription "$AZURE_SUBSCRIPTION_ID" \
  --location "$region" -o json > "$output_dir/aks-versions.json"

python3 "$repo_root/.github/utils/validate_aks_preflight.py" validate \
  --target-facts "$target_facts" \
  --expected-subscription "$AZURE_SUBSCRIPTION_ID" \
  --subscription "$output_dir/subscription.json" \
  --resource-skus "$output_dir/resource-skus.json" \
  --quota "$output_dir/quota.json" \
  --aks-versions "$output_dir/aks-versions.json" \
  --terraform-organization "$HCP_TERRAFORM_ORGANIZATION" \
  --terraform-workspace "$HCP_TERRAFORM_WORKSPACE" \
  --backend-output "$output_dir/backend.hcl" \
  > "$output_dir/validated-input.json"

terraform -chdir="$terraform_root" init \
  -backend-config="$output_dir/backend.hcl" -input=false
terraform -chdir="$terraform_root" plan -no-color -input=false \
  -out="$output_dir/create.tfplan" > "$output_dir/create-plan.txt"
terraform -chdir="$terraform_root" show -json "$output_dir/create.tfplan" \
  > "$output_dir/create-plan.json"

printf '%s\n' "AKS technical preflight passed; review $output_dir/create-plan.txt before requesting separate apply approval."
printf '%s\n' "A successful plan is not authorization to apply."
