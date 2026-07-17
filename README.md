# Halligalli Infrastructure

Public infrastructure repository for two explicit deployment targets: `container-apps`, the public Live Demo Environment, and `aks`, a maintained deployment-capable target. Neither target is called Production.

## Ownership

This repository owns Terraform, target-specific Deployment Desired State, independent manual Target Promotion lanes, deployment workflows, AKS Helm and Argo CD, observability, runbooks, and sanitized validation evidence. The [Product repository](https://github.com/optiplex331/Halligalli-BossYang) owns source, tests, formal Release Tags, paired Release Images, GitHub artifact provenance, and `paired-release-manifest.json`.

## Targets

| Target | Current role | Delivery model |
|---|---|---|
| `container-apps` | Continuously available Live Demo at `play.halligalli.games` | PR-gated desired state with an explicit local operator deployment |
| `aks` | Maintained deployment-capable target; last verified baseline `v0.7.2` | Target-scoped promotion and Argo CD GitOps reconciliation during approved validation runs |

Development Images are diagnostic only and cannot enter either formal promotion lane. One promotion changes exactly one target's desired-state file.

## Delivery controls

- `main` accepts changes through pull requests, requires the static validation check, requires resolved review conversations, and rejects force-pushes and deletion.
- Promotion workflows verify paired Web/API digests and GitHub artifact provenance before opening target-scoped Draft PRs. They cannot merge those PRs.
- Container Apps deployment is deliberately not executed by GitHub Actions. The operator reviews and merges desired state, signs in locally with `az login`, and runs [`scripts/deploy-container-apps.sh`](scripts/deploy-container-apps.sh).
- No Azure credential, user refresh token, service-principal secret, or publish profile is stored in GitHub.
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
