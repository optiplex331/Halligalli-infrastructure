# AKS Deployment Target

`aks` is a maintained deployment-capable target. It is not the current Live
Demo Environment, and checked-in desired state does not claim that an AKS
workload exists. This runbook is the single operational reference for the
target and for an explicitly approved AKS Validation Run.

The immutable, sanitized summary under `targets/aks/evidence/` is the sole owner of the
last completed run's release, dependency, platform, capability, and destruction
facts. Raw output and sensitive or identifying operation data stay outside Git.

## Ownership and desired state

Terraform owns Azure resources through the AKS cluster boundary. The Terraform
root describes one concrete target. Its checked-in `target.json` is the single
owner of the region, node SKU, node count, and Kubernetes patch version consumed
by Terraform and technical preflight. Resource names, network, identity, and
tags belong to the Terraform configuration.
Technical preflight derives per-node vCPU capacity and quota family from the
matched Azure SKU response before checking quota; these derived facts must not be
duplicated in prose or local configuration.

Argo CD owns the in-cluster runtime and observability Applications. Each
Application uses one Infrastructure-owned Chart source and a Values file
relative to that Chart. The runtime desired state owns the complete digest-pinned
Web/API pair, Redis digest, and operation-time ingress names. The Redis Secret
name is a fixed chart and operation constant. The observability desired state
owns the
Prometheus, OpenTelemetry Collector, and Tempo image digests. Grafana is not
part of the maintained disposable stack.

The runtime chart owns routing, replicas, rollout and disruption behavior,
topology spread, restricted security contexts, one chart-owned ServiceAccount;
the observability chart owns one equivalent chart-level ServiceAccount and
NetworkPolicies. Ingress sends public REST and WebSocket paths to API and all
other public paths to Web; internal API surfaces remain cluster-only. Redis is
ephemeral and receives a locally generated ACL Secret, never a credential in
Git. The chart schemas are the sole authority for values shape, required
fields, closed objects, non-empty rendered strings, and digest syntax. Helm
templates render those values without repeating schema validation; Kubernetes
owns platform resource-name validation.

The Product repository owns source, formal Release Tags, Release Images,
artifact provenance, and the Paired Release Manifest. `Target Promotion - AKS`
validates that evidence and proposes a Draft PR changing only the AKS desired
state. It cannot merge the PR, reconcile Argo CD, or deploy Azure resources.
Promotion establishes release trust once. Reviewers decide whether that Release
Tag should be deployed to AKS, confirm the target-scoped diff, and consider
operational blockers without manually repeating manifest, digest, or provenance
checks. A no-op promotion does not repeat provenance. Rollback restores a
complete previously reviewed Web/API pair without re-running promotion; mixed
selection, one-image rollback, and `kubectl rollout undo` are invalid.

## Safety boundary

Every Azure, Terraform remote-plan, apply, destroy, Kubernetes, Argo CD, DNS,
credential, disruption, rollback, and cleanup operation requires explicit
local-operation approval. Without it, stop. Do not substitute a different
subscription, region, SKU, version, release pair, DNS design, or historical
cluster.

Static tests, backendless Terraform validation, and Helm lint are read-only.
The OrbStack integration helper requires separate local approval before it
creates disposable Kubernetes resources. None of these checks establish an
AKS deployed state. A real Terraform plan may query remote state and acquire a
state lock, so it is also approval-gated. A successful plan never authorizes
apply.

## Static validation

From the repository root:

```bash
python3 -m unittest discover -s .github/utils/tests -p 'test_*.py'
actionlint
terraform -chdir=targets/aks/terraform fmt -check -recursive
terraform -chdir=targets/aks/terraform init -backend=false -input=false
terraform -chdir=targets/aks/terraform validate -no-color
helm lint targets/aks/gitops/halligalli --values targets/aks/gitops/halligalli/values/aks.values.json
helm lint targets/aks/gitops/observability --values targets/aks/gitops/observability/values/aks.values.json
```

These checks validate source, structured utilities, Terraform configuration,
and the chart schemas against checked-in values. After a promotion Draft PR is
created, the same static PR validation checks its updated AKS values. These
checks do not prove Azure networking, Argo CD reconciliation, multi-node
scheduling, disruption, DNS, rollback, cost, or destruction.

## Local OrbStack integration

OrbStack is the low-cost Kubernetes runtime seam. The repository-level static
commands above own chart linting; the integration helper only creates and
checks disposable local Kubernetes resources. It requires an explicit,
reviewed, digest-pinned values file and approval:

```bash
HALLIGALLI_ORBSTACK_VALUES=/path/to/values.json \
HALLIGALLI_ORBSTACK_APPROVED=1 \
targets/aks/scripts/orbstack-integration.sh
```

The helper checks runtime and observability rollouts, verifies every current
Ready Web/API Pod image digest, checks Ingress, Secrets, NetworkPolicies,
Prometheus and Tempo query paths, and exercises same-origin HTTPS behavior.
Use its `--help` output and source as the command contract. It does not prove
multi-node scheduling, Pod disruption, AKS networking, cloud DNS/TLS, Argo CD,
or Azure cost and teardown.

## Approval-gated preflight

An approved AKS Validation Run uses one ignored local operation configuration
and one preflight command:

```bash
cp targets/aks/terraform/local-operation.env.example targets/aks/terraform/local-operation.env
# Fill every field and record explicit approval in the ignored file.
targets/aks/scripts/aks-validation-preflight.sh
```

The script verifies the exact selected subscription, the fixed target region,
node SKU, checked-in Kubernetes patch, and available quota.
It trusts the reviewed `main` desired state that already passed static PR
validation, initializes the configured remote backend, and saves a Terraform
create plan under ignored `.local/` output. Review the saved plan and abort on
any mismatch. The script performs no cloud mutation, but its credentialed
reads and remote plan still require the operation approval described above.

## Approved validation procedure

Only after the preflight passes and each operation has explicit approval:

1. Record the Product release identity and digests, Infrastructure commit,
   dependency digests, selected Kubernetes patch, and known-good rollback pair
   in private run notes. Review and apply the exact Terraform plan, then record
   the resulting cluster shape privately.
2. Generate the Redis credential locally with
   `targets/aks/scripts/apply-redis-auth-secret.sh`. Bootstrap the controllers,
   apply both Argo CD Applications, and capture Synced/Healthy status. Do not
   treat a live patch as desired state.
3. After initial, rollback, and restored reconciliation, run
   `.github/utils/verify_running_pod_digests.py` against the checked-in runtime
   values to prove every current Ready Web/API business container reports the
   selected digest through its Pod `imageID`.
4. Verify the current same-origin Single-Player and multiplayer REST/WebSocket
   journeys. Confirm runtime placement and capture a bounded functional sample
   of accepted requests and commands. This is not a load claim.
5. Query Prometheus and Tempo through private-safe access and capture one
   correlated redacted log/trace plus internal operational checks. Never record
   credentials, Redis keys, room codes, nicknames, request payloads,
   kubeconfig, raw Secrets, account identifiers, or resource identifiers in
   public evidence.
6. With separate disruption approval, verify API Pod replacement,
   non-Redis-node drain and rescheduling, designed room loss after Redis
   replacement, and Argo CD self-heal after harmless desired-state drift.
7. Reconcile the complete known-good pair, prove running digests and smoke, then
   restore the selected pair and repeat those checks.
8. Capture sanitized results, review and execute the destroy plan, remove local
   sensitive material, and verify both Terraform state and provider inventory
   contain no remaining Halligalli AKS resources.

If any check fails, record the sanitized failure and prioritize safe cleanup.
Never mark an unexecuted or failed capability as passed.

## Evidence summaries

Do not create an empty evidence template. Each run adds one concise, dated
`targets/aks/evidence/validation-YYYY-MM-DD.json` summary only after field-by-field
sanitization. A future summary must contain:

- a schema version, run date, and final `passed` or `failed` status;
- the Infrastructure commit and complete Product release identity: Release
  Tag, Product commit, Web digest, API digest, and Redis digest;
- the selected Kubernetes patch and immutable observability dependency digests;
- one explicit result for preflight, Argo CD reconciliation, running Pod
  digests, public journeys, observability, each approved disruption, paired
  rollback and restore, and destroy plus empty-inventory verification;
- whether a live workload remains, links to sanitized durable artifacts when
  any are published, and short notes needed to qualify a claim.

Use `passed`, `failed`, or `not-run` for individual results. A successful run
requires destroy and empty-inventory verification to pass and no retained
Halligalli workload. Failed runs may publish a summary only when it improves
future diagnosis and is safe to disclose. Never include secrets, raw command
output, billing details, account or resource identifiers, kubeconfig, or
secret-bearing manifests.

The existing completed summary is historical and remains unchanged; its fields
describe only what that run executed and must not be reinterpreted as evidence
for the current charts or a later journey contract.
