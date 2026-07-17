#!/usr/bin/env sh
# Performs no cloud mutations. It writes local validation evidence and Terraform init may
# acquire a remote state lock after local operation approval.
set -eu

if [ "${HALLIGALLI_OPERATION_APPROVED:-}" != "1" ]; then
  echo "Refusing Azure preflight without HALLIGALLI_OPERATION_APPROVED=1." >&2
  exit 1
fi

for command in az terraform curl gh python3; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "AKS preflight requires $command in PATH; do not install it from this helper." >&2
    exit 1
  }
done

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)"
terraform_root="$repo_root/terraform/aks"
output_dir="${HALLIGALLI_AKS_PREFLIGHT_OUTPUT:-$repo_root/.local/aks-portfolio-proof-preflight}"
region="${HALLIGALLI_AKS_REGION:-westeurope}"
sku="Standard_D4ls_v6"
deadline_utc="${HALLIGALLI_AKS_PROOF_DEADLINE_UTC:-}"
dns_choice="${HALLIGALLI_AKS_PROOF_DNS_CHOICE:-}"
target_version="${HALLIGALLI_AKS_KUBERNETES_VERSION:-}"
release_tag="${HALLIGALLI_AKS_PROOF_RELEASE_TAG:-}"
product_repository="${HALLIGALLI_AKS_PROOF_PRODUCT_REPOSITORY:-}"
minimum_credit_usd="${HALLIGALLI_AKS_MINIMUM_CREDIT_USD:-}"

[ "$region" = "westeurope" ] || {
  echo "Refusing unreviewed region '$region'; the proof target is westeurope." >&2
  exit 1
}
[ -n "$deadline_utc" ] && [ -n "$target_version" ] && [ -n "$release_tag" ] && [ -n "$product_repository" ] || {
  echo "Set the proof deadline, Kubernetes version, Product repository, and formal Paired Release tag." >&2
  exit 1
}
case "$dns_choice" in
  local-ingress|temporary-dns) ;;
  *)
    echo "HALLIGALLI_AKS_PROOF_DNS_CHOICE must be local-ingress or temporary-dns." >&2
    exit 1
    ;;
esac

mkdir -p "$output_dir"
mkdir -p "$output_dir/published-release"
gh release download "$release_tag" --repo "$product_repository" \
  --pattern paired-release-manifest.json --dir "$output_dir/published-release"
gh api "repos/$product_repository/git/ref/tags/$release_tag" \
  > "$output_dir/published-release/tag-ref.json"
tag_object_type="$(python3 - "$output_dir/published-release/tag-ref.json" <<'PY'
import json
import sys
from pathlib import Path

print(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["object"]["type"])
PY
)"
if [ "$tag_object_type" = "tag" ]; then
  tag_object_sha="$(python3 - "$output_dir/published-release/tag-ref.json" <<'PY'
import json
import sys
from pathlib import Path

print(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["object"]["sha"])
PY
)"
  gh api "repos/$product_repository/git/tags/$tag_object_sha" \
    > "$output_dir/published-release/tag-object.json"
fi

az account show --query '{id:id,name:name,tenantId:tenantId,state:state}' -o json \
  > "$output_dir/subscription.json"
subscription_id="$(az account show --query id -o tsv)"
if [ -n "$minimum_credit_usd" ]; then
  billing_property_url="https://management.azure.com/subscriptions/$subscription_id/providers/Microsoft.Billing/billingProperty/default?api-version=2024-04-01"
  az rest --method get --url "$billing_property_url" -o json > "$output_dir/billing-property.json"

  billing_profile_id="$(python3 - "$output_dir/billing-property.json" <<'PY'
import json
import sys
from pathlib import Path

properties = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["properties"]
profile_id = properties.get("billingProfileId")
if not profile_id:
    raise SystemExit("The subscription does not expose an MCA billing profile for credit verification.")
print(profile_id)
PY
)"
  credit_url="https://management.azure.com${billing_profile_id}/providers/Microsoft.Consumption/credits/balanceSummary?api-version=2023-11-01"
  az rest --method get --url "$credit_url" -o json > "$output_dir/subscription-credit.json"

  python3 - "$output_dir/subscription-credit.json" "$minimum_credit_usd" <<'PY'
import json
import sys
from pathlib import Path

properties = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["properties"]
minimum = float(sys.argv[2])
summary = properties.get("balanceSummary", {})
current = summary.get("currentBalance", {})
estimated = summary.get("estimatedBalance", {})
if current.get("currency") != "USD" or estimated.get("currency") != "USD":
    raise SystemExit("The configured credit-floor check requires an auditable USD balance.")
if min(float(current.get("value", 0)), float(estimated.get("value", 0))) < minimum:
    raise SystemExit("The current or estimated credit balance is below the configured threshold.")
PY
fi

resource_skus_url="https://management.azure.com/subscriptions/$subscription_id/providers/Microsoft.Compute/skus?api-version=2021-07-01&%24filter=location%20eq%20%27$region%27"
az rest --method get --url "$resource_skus_url" -o json > "$output_dir/resource-skus.json"
python3 - "$sku" "$region" "$output_dir/resource-skus.json" \
  > "$output_dir/sku.json" <<'PY'
import json
import sys
from pathlib import Path

sku, region, source = sys.argv[1:]
items = json.loads(Path(source).read_text(encoding="utf-8"))["value"]
matches = [
    item
    for item in items
    if item.get("name") == sku
    and region.casefold() in {location.casefold() for location in item.get("locations", [])}
]
if len(matches) != 1:
    raise SystemExit(f"Expected exactly one {sku} Resource SKU entry in {region}; found {len(matches)}.")
selected = matches[0]
if selected.get("restrictions"):
    raise SystemExit(f"{sku} has subscription restrictions in {region}.")
print(json.dumps({
    "name": selected["name"],
    "locations": selected["locations"],
    "restrictions": selected.get("restrictions", []),
    "capabilities": selected.get("capabilities", []),
}, indent=2))
PY
az vm list-usage --location "$region" -o json > "$output_dir/quota.json"
python3 - "$output_dir/quota.json" <<'PY'
import json
import sys
from pathlib import Path

usage = {
    item["name"]["value"]: (int(item["currentValue"]), int(item["limit"]))
    for item in json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
}
for quota_name in ("cores", "StandardDlsv6Family"):
    if quota_name not in usage:
        raise SystemExit(f"Required Azure quota {quota_name} was not returned.")
    current, limit = usage[quota_name]
    if limit - current < 8:
        raise SystemExit(f"Required Azure quota {quota_name} has fewer than 8 available vCPUs.")
PY
az aks get-versions --location "$region" -o json > "$output_dir/aks-versions.json"

python3 "$repo_root/.github/utils/validate_paired_release_manifest.py" \
  "$output_dir/published-release/paired-release-manifest.json" \
  --expected-tag "$release_tag" \
  --output "$output_dir/published-release/release-candidate.json"

python3 - "$deadline_utc" "$target_version" "$dns_choice" "$output_dir/aks-versions.json" \
  "$release_tag" "$output_dir/published-release/paired-release-manifest.json" \
  "$output_dir/published-release/release-candidate.json" \
  "$output_dir/published-release/tag-ref.json" "$output_dir/published-release/tag-object.json" \
  "$repo_root/gitops/aks/values/halligalli.values.json" \
  > "$output_dir/preflight-input.json" <<'PY'
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

deadline = datetime.fromisoformat(sys.argv[1].replace("Z", "+00:00"))
now = datetime.now(timezone.utc)
if deadline.tzinfo is None or not now < deadline <= now + timedelta(hours=4):
    raise SystemExit("HALLIGALLI_AKS_PROOF_DEADLINE_UTC must be a UTC deadline within four hours.")

versions = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8"))
serialized = json.dumps(versions)
if sys.argv[2] not in serialized:
    raise SystemExit("Selected Kubernetes version is not currently offered in the target region.")

release_tag, manifest_path, candidate_path, tag_ref_path, tag_object_path, values_path = sys.argv[5:]
manifest_bytes = Path(manifest_path).read_bytes()
candidate = json.loads(Path(candidate_path).read_text(encoding="utf-8"))
product_commit = candidate["commit"]
tag_ref = json.loads(Path(tag_ref_path).read_text(encoding="utf-8"))["object"]
tag_commit = tag_ref["sha"]
if tag_ref["type"] == "tag":
    tag_object = json.loads(Path(tag_object_path).read_text(encoding="utf-8"))["object"]
    if tag_object["type"] != "commit":
        raise SystemExit("Nested annotated Product tags are not accepted for the proof.")
    tag_commit = tag_object["sha"]
if product_commit != tag_commit:
    raise SystemExit("The published manifest commit must equal the Product release tag commit.")

values = json.loads(Path(values_path).read_text(encoding="utf-8"))
if values.get("releaseVersion") != candidate["version"]:
    raise SystemExit("Infrastructure GitOps release label does not match the published Paired Release version.")
for role, values_key in (("web", "webImage"), ("api", "apiImage")):
    selected = values.get(values_key, {})
    if selected.get("repository") != candidate[f"{role}_repository"] or selected.get("digest") != candidate[f"{role}_digest"]:
        raise SystemExit(f"Infrastructure GitOps does not select the attested {role} image.")

print(json.dumps({
    "deadlineUtc": sys.argv[1],
    "targetKubernetesVersion": sys.argv[2],
    "dnsChoice": sys.argv[3],
    "pairedRelease": {
        "releaseTag": release_tag,
        "productCommit": product_commit,
        "webDigest": candidate["web_digest"],
        "apiDigest": candidate["api_digest"],
        "manifestSha256": hashlib.sha256(manifest_bytes).hexdigest(),
    },
}, indent=2))
PY

# The retail API is public and read-only. Keep its response as evidence because
# price is volatile; the operator records the selected meter and estimate in the
# evidence record rather than treating this raw response as a cost assertion.
curl --fail --silent --show-error --get \
  --data-urlencode "\$filter=serviceName eq 'Virtual Machines' and armRegionName eq 'westeurope' and contains(skuName, 'D4ls v6')" \
  'https://prices.azure.com/api/retail/prices' > "$output_dir/retail-prices.json"

[ -n "${TERRAFORM_BACKEND_CONFIG_PATH:-}" ] && [ -n "${TERRAFORM_TFVARS_JSON_PATH:-}" ] || {
  echo "Set TERRAFORM_BACKEND_CONFIG_PATH and TERRAFORM_TFVARS_JSON_PATH before the approved preflight." >&2
  exit 1
}

terraform -chdir="$terraform_root" init \
  -backend-config="$TERRAFORM_BACKEND_CONFIG_PATH" -input=false
terraform -chdir="$terraform_root" plan -no-color -input=false \
  -var-file="$TERRAFORM_TFVARS_JSON_PATH" \
  -out="$output_dir/create.tfplan" > "$output_dir/create-plan.txt"
terraform -chdir="$terraform_root" show -json "$output_dir/create.tfplan" \
  > "$output_dir/create-plan.json"

printf '%s\n' "Non-cloud-mutating AKS preflight facts captured in $output_dir; local evidence was written and Terraform may have acquired a state lock."
printf '%s\n' "Review the procedure, record an abort/pass result, and obtain a fresh approval before any mutation."
