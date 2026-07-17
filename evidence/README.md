# Validation evidence

This public repository retains only deliberately sanitized validation summaries
and the reusable evidence-record template. Raw command output, account and
resource identifiers, billing data, kubeconfig, credentials, Terraform plans,
and failed-attempt records stay outside Git.

New validation runs begin from `aks-portfolio-proof-record.template.json` in an
ignored local path. Publish a reduced summary only after reviewing every field.
