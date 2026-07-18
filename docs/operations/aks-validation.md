# AKS Validation Procedure

This is the repeatable procedure for an explicitly approved `aks` Validation Run. It is
not evidence that a workload currently exists. A sanitized summary of the completed
2026-07-13 run is recorded separately in
[`evidence/aks-validation-summary.json`](../../evidence/aks-validation-summary.json),
and no Halligalli workload remains deployed on AKS. The historical standalone proof is
not reusable paired-runtime evidence.

## Approval boundary

Every Azure, Terraform remote-plan, Kubernetes, Argo CD, DNS, disruptive,
rollback, and destroy command requires explicit local-operation approval.
Without it, stop. Do not substitute another subscription, SKU, region, version,
release pair, DNS approach, or a stopped historical cluster.

The checked-in helper performs no cloud mutations and refuses to run unless the
one ignored operation configuration contains `HALLIGALLI_OPERATION_APPROVED=1`.
It writes ignored local validation output, and Terraform planning may acquire a
remote state lock:

```bash
cd /path/to/Halligalli-infrastructure
cp terraform/aks/local-operation.env.example terraform/aks/local-operation.env
# Fill the exact subscription, Terraform Cloud organization/workspace, full
# Kubernetes patch version, and explicit approval in the ignored file.
gitops/aks/scripts/aks-validation-preflight.sh
```

It verifies the exact subscription, regional `Standard_D4ls_v6` availability
and restrictions, regional quota, supported selected AKS version, and checked-in
GitOps desired state, then writes a Terraform create plan under ignored
`.local/`. The operator must review the plan and abort on any mismatch. A plan
does not authorize apply.

## Approved execution checklist

Only after a passing preflight and the same explicit approval:

1. Start the four-hour UTC timer; record Product commit/tag, paired Web/API
   digests, Infrastructure commit, Redis/observability digests, and the selected
   known-good rollback pair. Create the AKS boundary, then record both node
   names, versions, and SKU.
2. Create the Redis credential only locally with the existing approval-gated
   helper. Bootstrap controllers, apply both Argo CD Applications, and capture
   Synced/Healthy status. No live patch is final desired state. After each
   initial, rollback, and restored reconcile, run
   `.github/utils/verify_running_pod_digests.py --values gitops/aks/values/halligalli.values.json --namespace halligalli --rollout-timeout 180s`
   to prove every current Ready Web/API business container reports the selected
   digest through its Pod `imageID`.
3. Verify same-origin single-player plus four-seat/two-human and
   eight-seat/two-human REST/WebSocket journeys. Capture two Web and two API
   Pods across the two nodes and the Redis Pod. Send at least 50 valid REST
   requests and 50 accepted commands across two rooms; this is a functional
   observability sample, not a load claim.
4. Capture the private-safe dashboard, one correlated structured log/trace, and
   internal operational-endpoint checks. Never place credentials, Redis keys,
   room codes, nicknames, request payloads, kubeconfig, or raw Secrets in the
   evidence record or screenshots. The public summary deliberately omits account,
   billing, node, operator, and resource identifiers retained during a private run.
5. With approval still active, delete one API Pod; drain the node not hosting
   Redis and verify rescheduling; delete Redis with active rooms and record the
   designed room-ending behavior. Then make one harmless replica drift and
   record Argo CD self-heal.
6. Move GitOps as a complete pair to the known-good Paired Release and prove
   the running Pod digests plus public smoke. Do not use a one-image rollback or
   `kubectl rollout undo`.
7. Before the deadline, capture sanitized artifacts, execute the reviewed
   destroy plan, remove local credentials/material, and verify Terraform state
   plus Azure inventory are empty for both the proof and node resource groups.
   Record actual cost and UTC end time.

If a check fails, capture its sanitized result, proceed only if the approved
window still permits safe destruction, and never mark the proof passed.

## Evidence record rules

Copy the template into ignored `.local/` for each run. It binds all artifacts to
one proof identity and keeps facts that are not executed as `not-run`. Link
sanitized files or stable external artifact URLs rather than pasting command
output. The record must contain no secret values or secret-bearing manifests.
The current template uses schema V2 journey names for four-seat/two-human and
eight-seat/two-human validation. The sanitized 2026-07-13 summary records only
that the earlier same-origin journey contract passed and must not imply that the
later journey contract was run.

The required final status is either `passed`, `failed`, or `destroyed`; a
successful AKS Validation Run additionally requires
`destroyAndInventory: "passed"` and no remaining Halligalli workload.
