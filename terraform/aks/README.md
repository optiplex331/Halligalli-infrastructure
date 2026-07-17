# AKS Deployment Target Terraform Root

This root models the Azure boundary for an approval-gated two-node AKS
Validation Run. It does not imply a live target and must not be
planned against remote state, applied, destroyed, or connected to DNS without
explicit local-operation approval.

## Resource shape

- one proof resource group and one explicit AKS node resource group;
- AKS Base/Free control plane in `westeurope`;
- one system pool with exactly two `Standard_D4ls_v6` nodes and 64 GiB disks;
- explicit VNet, AKS subnet, network security group, and user-assigned identity;
- Azure CNI with the fixed proof network envelope;
- no Azure DNS, Application Gateway, ACR, database, persistent Redis, managed
  telemetry, autoscaling, Spot nodes, or additional node pools.

Terraform stops at the AKS cluster boundary. Argo CD owns in-cluster runtime and
observability resources from `gitops/aks/`.

## Static validation

```bash
terraform -chdir=terraform/aks fmt -check -recursive
terraform -chdir=terraform/aks init -backend=false -input=false
terraform -chdir=terraform/aks validate -no-color
python3 -m unittest discover -s .github/utils/tests -p 'test_*.py'
```

Backendless validation does not read remote state and is safe without cloud
credentials. Do not use `terraform apply` as a validation shortcut.

## Approved operation model

The approval-gated preflight generates ignored backend/tfvars material, checks
regional SKU restrictions and quota, an optional configured credit floor,
retail pricing, selected AKS patch, formal Paired Release, deadline, DNS choice,
and an exact Terraform create plan. Any mismatch aborts rather than selecting a
fallback SKU, region, version, release, or DNS path.

The validation lifecycle is create, prove, capture sanitized evidence, destroy,
then verify empty Terraform state and absence of both resource groups. Follow
[`docs/operations/aks-validation.md`](../../docs/operations/aks-validation.md)
for the complete approval and evidence contract.

The 2026-07-13 run used AKS `1.35.5` and two `Standard_D4ls_v6` nodes, then
completed the reviewed six-delete plan. The successful record intentionally
leaves `actualCost` null because an attributable charge had not posted before
teardown; it does not substitute an estimate.
