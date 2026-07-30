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

Argo CD owns the cert-manager, runtime, and observability Applications. The
cert-manager Application consumes a pinned upstream Helm chart and installs the
cert-manager CRDs and controllers into the `cert-manager` namespace. The
runtime and observability Applications use Infrastructure-owned Chart sources
and Values files relative to those Charts. The runtime desired state owns the
complete digest-pinned Web/API pair, Redis digest, and operation-time ingress
names. Its chart also owns the ACME `ClusterIssuer` resources and the explicit
`Certificate` that produces the `halligalli-tls` Secret for
`aks.halligalli.games`. The cert-manager ACME account keys and issued TLS
private key are generated and stored in the cluster, never in Git. The Redis
Secret name is a fixed chart and operation constant. The observability desired
state owns the
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
checks do not prove Azure networking, Argo CD or cert-manager reconciliation,
multi-node scheduling, disruption, public DNS/TLS, rollback, cost, or
destruction.

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

The helper requires its disposable namespace to be absent before it starts,
verifies every current Ready Web/API Pod image digest, and exercises
same-origin HTTPS behavior through Ingress. It deletes the namespace when the
smoke exits.
It explicitly disables the runtime chart's cert-manager resources and uses a
short-lived locally generated self-signed TLS Secret, so it does not validate
the observability chart, cert-manager, ACME, public DNS, or public certificate
trust.
It does not prove multi-node scheduling, Pod disruption, AKS networking, cloud
DNS/TLS, Argo CD, or Azure cost and teardown.

## Approval-gated preflight

An approved AKS Validation Run uses ignored local operation and backend
configurations plus one preflight command:

```bash
cp targets/aks/terraform/local-operation.env.example targets/aks/terraform/local-operation.env
cp targets/aks/terraform/backend.hcl.example targets/aks/terraform/backend.hcl
# Select the subscription, record explicit approval, and configure the reviewed
# HCP Terraform organization and workspace in the ignored files.
targets/aks/scripts/aks-validation-preflight.sh
```

The script verifies that the exact selected subscription is enabled, trusts the
reviewed `main` desired state that already passed static PR validation,
initializes the configured remote backend, and saves a Terraform create plan
under ignored `.local/` output. Review the saved plan and abort on any mismatch.
The script performs no cloud mutation, but its credentialed subscription read
and remote plan still require the operation approval described above.

## cert-manager and public TLS

The runtime target uses `aks.halligalli.games` and the public ACME contact
`optiplex331@gmail.com`. The contact address and hostname are public desired
state, not credentials. The `halligalli-tls` Secret, the ACME account key
Secrets, and certificate private key are created by cert-manager in the cluster
and must never be committed, printed, or captured in evidence.

The DNS record for `aks.halligalli.games` must point to the public address of
the `nginx` Ingress controller before certificate issuance. HTTP port 80 and
HTTPS port 443 must be reachable from the public Internet, and the controller
must expose the `nginx` IngressClass. DNS changes and Kubernetes operations are
separately approved operations; this runbook does not authorize them.

This repository does not install `ingress-nginx`; that controller remains part
of the separately approved cluster bootstrap. Before applying cert-manager,
verify the bootstrap-owned controller and its public load balancer:

```bash
kubectl get ingressclass nginx
kubectl -n ingress-nginx get service -o wide
```

Create the `aks.halligalli.games` A/AAAA record at the approved DNS provider
using the controller's public address, then verify the record from an external
network before starting ACME issuance.

The cert-manager Application is pinned to Helm chart `v1.21.0` and enables
CRDs. The runtime chart creates both `letsencrypt-staging` and
`letsencrypt-prod` `ClusterIssuer` resources with the HTTP-01 solver and
creates the target `Certificate`. The checked-in target intentionally selects
`letsencrypt-staging` so the first public DNS and HTTP-01 validation cannot
consume production rate limits. After the staging Certificate is Ready and
the public HTTPS path is verified, change `tls.clusterIssuer` to
`letsencrypt-prod` through a separate reviewed desired-state change. Do not
switch issuers with a live `kubectl patch`.

After the controllers and Argo CD are bootstrapped, apply the cert-manager
Application first and wait for its CRDs and deployments:

Do not bulk-apply the files in `targets/aks/gitops/applications/`; the
cert-manager Application must become Healthy before the runtime Application is
created. The Application sync-wave annotations also preserve this order when a
parent Argo CD Application manages these child Applications.

```bash
kubectl apply -f targets/aks/gitops/applications/cert-manager.application.yaml
kubectl -n argocd wait --for=jsonpath='{.status.sync.status}'=Synced \
  application/cert-manager --timeout=600s
kubectl -n argocd wait --for=jsonpath='{.status.health.status}'=Healthy \
  application/cert-manager --timeout=600s
kubectl wait --for=condition=Established \
  crd/certificates.cert-manager.io \
  crd/clusterissuers.cert-manager.io \
  crd/orders.acme.cert-manager.io \
  crd/challenges.acme.cert-manager.io \
  --timeout=120s
kubectl -n cert-manager rollout status deployment/cert-manager --timeout=180s
kubectl -n cert-manager rollout status deployment/cert-manager-webhook --timeout=180s
kubectl -n cert-manager rollout status deployment/cert-manager-cainjector --timeout=180s
```

Then apply the runtime and observability Applications. The runtime
`ClusterIssuer` and `Certificate` resources must reconcile only after the
cert-manager CRDs and controllers are ready:

```bash
kubectl apply -f targets/aks/gitops/applications/halligalli.application.yaml
kubectl apply -f targets/aks/gitops/applications/halligalli-observability.application.yaml
kubectl -n argocd wait --for=jsonpath='{.status.sync.status}'=Synced \
  application/halligalli application/halligalli-observability --timeout=600s
kubectl -n argocd wait --for=jsonpath='{.status.health.status}'=Healthy \
  application/halligalli application/halligalli-observability --timeout=600s
kubectl wait --for=condition=Ready \
  clusterissuer/letsencrypt-staging \
  clusterissuer/letsencrypt-prod \
  --timeout=300s
kubectl -n halligalli wait --for=condition=Ready \
  certificate/halligalli-ingress --timeout=600s
kubectl -n halligalli get secret halligalli-tls \
  -o jsonpath='{.type}{"\n"}'
kubectl -n halligalli get ingress halligalli -o wide
```

The Secret check must return `kubernetes.io/tls`. A staging certificate is
expected to be untrusted by normal browsers; inspect the presented issuer and
hostname, but do not treat browser trust as passed until the reviewed issuer
change selects `letsencrypt-prod`. Never use `kubectl get secret -o yaml` in
shared notes. Confirm the public path with a read-only request. The staging
issuer is not browser-trusted, so this first check intentionally skips
certificate trust:

```bash
curl --fail --silent --show-error --insecure https://aks.halligalli.games/
```

After the reviewed switch to `letsencrypt-prod`, repeat the request without
`--insecure` and record the trusted HTTPS result.

The issuer switch is a separate desired-state change. Before merging it,
record the current Certificate revision:

```bash
previous_revision="$(kubectl -n halligalli get certificate halligalli-ingress \
  -o jsonpath='{.status.revision}')"
```

After the production desired state reconciles, verify that cert-manager has
issued a new revision rather than merely retaining the staging Secret:

```bash
kubectl -n halligalli wait --for=condition=Ready \
  certificate/halligalli-ingress --timeout=600s
current_revision="$(kubectl -n halligalli get certificate halligalli-ingress \
  -o jsonpath='{.status.revision}')"
test -n "$current_revision" && test "$current_revision" -gt "${previous_revision:-0}"
kubectl -n halligalli get certificate halligalli-ingress \
  -o jsonpath='{.spec.issuerRef.name}{"\n"}'
kubectl -n halligalli get secret halligalli-tls \
  -o jsonpath='{.type}{"\n"}'
curl --fail --silent --show-error https://aks.halligalli.games/
```

The final `issuerRef` must be `letsencrypt-prod`, the Secret type must be
`kubernetes.io/tls`, and the trusted HTTPS request must pass before recording
the production TLS capability as verified.

For issuance failures, inspect `Certificate`, `Order`, and `Challenge`
status and events without exposing Secret data. cert-manager owns renewal;
verify `Certificate` readiness and `status.notAfter` during an approved run.
Do not delete the ACME account key or TLS Secret as a first recovery action.

## Approved validation procedure

Only after the preflight passes and each operation has explicit approval:

1. Record the Product release identity and digests, Infrastructure commit,
   dependency digests, selected Kubernetes patch, and known-good rollback pair
   in private run notes. Review and apply the exact Terraform plan, then record
   the resulting cluster shape privately.
2. Generate the Redis credential locally with
   `targets/aks/scripts/apply-redis-auth-secret.sh`. Bootstrap the controllers,
   apply the cert-manager Application first, wait for its CRDs and controller
   deployments, then apply the runtime and observability Applications. Capture
   Synced/Healthy status for all three Applications and Ready status for the
   runtime `Certificate`. Do not treat a live patch as desired state.
3. After initial, rollback, and restored reconciliation, run
   `.github/utils/verify_running_pod_digests.py` against the checked-in runtime
   values to prove every current Ready Web/API business container reports the
   selected digest through its Pod `imageID`.
4. Verify the staging same-origin HTTPS Single-Player and multiplayer
   REST/WebSocket journeys at `https://aks.halligalli.games` with the
   explicitly documented staging trust exception. Complete the reviewed
   staging-to-production issuer change, verify the new Certificate revision
   and trusted HTTPS request, then repeat the same journeys without
   `--insecure`. Confirm runtime placement and capture a bounded functional
   sample of accepted requests and commands. This is not a load claim.
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
