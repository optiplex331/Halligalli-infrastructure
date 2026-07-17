# Halligalli Infrastructure

Public infrastructure repository for two explicit deployment targets: `container-apps`, the public Live Demo Environment, and `aks`, a maintained deployment-capable target. Neither target is called Production.

## Ownership

This repository owns Terraform, target-specific Deployment Desired State, independent manual Target Promotion lanes, deployment workflows, AKS Helm and Argo CD, observability, runbooks, and sanitized validation evidence. The [Product repository](https://github.com/optiplex331/Halligalli-BossYang) owns source, tests, formal Release Tags, paired Release Images, GitHub artifact provenance, and `paired-release-manifest.json`.

## Targets

| Target | Current role | Delivery model |
|---|---|---|
| `container-apps` | Intended continuously available Live Demo at `play.halligalli.games`; live activation is not proven by repository state | PR-gated IaC/CD with revision-safe post-merge deployment |
| `aks` | Maintained deployment-capable target; last verified baseline `v0.7.2` | Target-scoped promotion and Argo CD GitOps reconciliation during approved validation runs |

Development Images are diagnostic only and cannot enter either formal promotion lane. One promotion changes exactly one target's desired-state file.

## Delivery controls

- `main` accepts changes through pull requests, requires the static validation check, requires resolved review conversations, and rejects force-pushes and deletion.
- Promotion workflows verify paired Web/API digests and GitHub artifact provenance before opening target-scoped Draft PRs. They cannot merge those PRs.
- The `container-apps` and `aks` GitHub Environments allow deployments only from protected branches and require an explicit review from the repository owner.
- `AZURE_CREDENTIALS`, when configured, belongs only to the target Environment that consumes it. The service principal must be scoped to the target resource group and must not receive subscription-wide roles.
- Actions are restricted to GitHub-owned and verified publishers. Every referenced action is pinned to a full commit SHA.

## Local validation

```bash
python3 -m unittest discover -s .github/utils/tests -p 'test_*.py'
actionlint
terraform -chdir=terraform/container-apps fmt -check -recursive
terraform -chdir=terraform/container-apps init -backend=false -input=false
terraform -chdir=terraform/container-apps validate -no-color
terraform -chdir=terraform/aks fmt -check -recursive
terraform -chdir=terraform/aks init -backend=false -input=false
terraform -chdir=terraform/aks validate -no-color
helm lint gitops/aks/chart/halligalli --values gitops/aks/values/halligalli.values.json
helm lint gitops/aks/chart/halligalli-observability --values gitops/aks/values/halligalli-observability.values.json
```

These commands are static validation only. Never use a cloud apply as validation.

See [Container Apps Live Demo](docs/operations/container-apps.md), [AKS Target](docs/operations/aks.md), and [AKS Validation Procedure](docs/operations/aks-validation.md).
