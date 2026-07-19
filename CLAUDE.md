# Agent Instructions - Halligalli Infrastructure

Public infrastructure repository for the Halligalli `container-apps` and `aks`
deployment targets. Current architecture and commands live in `README.md` and
the target runbooks under `docs/operations/`.

## Safety boundary

- Never run Azure, Kubernetes, Argo CD, DNS, Terraform apply/destroy, remote
  plan, credential, disruption, rollback, or cleanup operations without
  explicit local-operation approval.
- Backendless Terraform validation, utility tests, actionlint, and Helm lint
  are static checks; they neither authorize nor prove a deployment.
- Keep credentials, backend configuration, plans, state, local operation
  configuration, and unsanitized evidence out of Git.

## Delivery ownership

- Promotion establishes formal Web/API release binding and artifact provenance.
- Pull request review owns deployment intent, target scope, operational blockers,
  and complete rollback selection.
- Container Apps Terraform should validate only the deployment inputs it
  consumes; do not duplicate release provenance or another layer's validation.

## Workflow

- Check Git status before editing and keep commits scoped to this repository.
- Preserve unrelated work and use the repository's existing validation tools.
- Use Conventional Commits (`<type>(<scope>): <summary>`).
