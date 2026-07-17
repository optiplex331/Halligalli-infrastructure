# AKS Deployment Desired State

This directory is the Infrastructure-owned desired state for Halligalli's
maintained AKS Deployment Target. Desired state is not evidence of a live
deployment: `v0.7.2` is the last verified baseline, its validation resources
were destroyed, and newer selections remain deployment-capable until proven.

## Layout

| Path | Purpose |
|---|---|
| `applications/halligalli.application.json` | Argo CD Application for the paired Web/API/Redis runtime. |
| `applications/halligalli-observability.application.json` | Argo CD Application for the disposable Prometheus/Grafana/Collector/Tempo proof stack. |
| `chart/halligalli/` | Closed paired-runtime chart: two Web Pods, two API Pods, one ephemeral Redis Pod. |
| `chart/halligalli-observability/` | Closed minimal observability proof chart. |
| `values/halligalli.values.json` | Paired Web/API digests, Redis digest, display-only release version, and operation-time ingress/Secret names. |
| `values/halligalli-observability.values.json` | Immutable observability dependency selection. |
| `scripts/` | Approval-gated preflight, Redis Secret, and OrbStack validation helpers. |

The two Applications use Argo CD multi-source configuration: chart templates
and values both come from this repository at `main`. Terraform records the AKS
and GitOps boundary but does not apply Kubernetes resources.

## Paired release selection

The deployable Product identity is one complete pair:

```text
vX.Y.Z schema-V2 Paired Release Manifest
  -> webImage.repository@webImage.digest
  -> apiImage.repository@apiImage.digest
  -> display-only releaseVersion
```

`Target Promotion - AKS` verifies the manifest and each immutable digest against the exact
Product repository, signer workflow, source tag ref, and source commit, then
runs a digest-pinned Web/API/Redis readiness and same-origin smoke before
changing these fields.
It never merges the Draft PR or syncs Argo CD. Rollback changes the complete
pair; mixed versions and one-image rollback are invalid.

## Runtime boundary

Ingress routes `/api/v1` and `/ws/v1` to API and `/` to Web. Internal identity,
readiness, and metrics endpoints remain behind the API Service. Redis is
ephemeral and receives its ACL through an existing locally generated Secret,
never through Git values.

The runtime chart fixes replicas, disruption budgets, topology spread,
restricted security contexts, read-only filesystems, dedicated ServiceAccounts,
and minimum-flow NetworkPolicies. Its schema rejects speculative knobs.

Apply either Application, change the selected pair, sync Argo CD, or move DNS
only inside an explicitly approved proof window. See the
[AKS Validation Procedure](../../docs/operations/aks-validation.md).

## Validation

```bash
python3 -m unittest discover -s .github/utils/tests -p 'test_*.py'
```

These are static checks; they do not prove Azure resources or a live cluster
exist. Approved OrbStack, AKS reconcile, rollback, and restore paths use
`.github/utils/verify_running_pod_digests.py` to compare every current Ready
Web/API Pod `imageID` with the selected values. Functional smoke is still
required separately. The completed proof evidence is stored under `evidence/`.
