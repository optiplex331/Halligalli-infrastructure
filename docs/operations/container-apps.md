# Container Apps Live Demo

`container-apps` is the target for the continuously available Live Demo Environment at `https://play.halligalli.games`. It uses PR-gated desired state plus an explicit local operator deployment, is not GitOps, and has no public API domain. Checked-in desired state and static validation do not prove that a separately approved live deployment has occurred.

## Runtime and cost target

One Azure Container App contains three separate containers sharing localhost networking:

| Container | Purpose | CPU | Memory |
|---|---|---:|---:|
| Web | nginx public gateway on port 8080 | 0.12 vCPU | 0.25 GiB |
| API | FastAPI on localhost:8000 | 0.26 vCPU | 0.5 GiB |
| Redis | ephemeral Redis on localhost:6379 with persistence disabled | 0.12 vCPU | 0.25 GiB |

The initial app total is 0.5 vCPU / 1 GiB with `minReplicas = 1` and `maxReplicas = 1`. The monthly budget target is USD 25. An approved ephemeral platform test on 2026-07-17 showed that Azure rejects the original `0.125 / 0.25 / 0.125` split because each container CPU value may have at most two decimal places; Azure accepted the nearest symmetric `0.12 / 0.26 / 0.12` split without changing the total.

Creating the DNS validation records, managed certificate, and `play.halligalli.games` binding is a separately approved bootstrap operation. AzureRM exposes the app's custom-domain collection as read-only, so this repository does not pretend that Terraform owns that binding or hide it behind deployment.

## Bootstrap order

Bootstrap uses Azure AD authentication and remote Terraform state. Create the
state resource group, storage account, and private `tfstate` container first,
then copy `terraform/container-apps/backend.hcl.example` to the ignored
`backend.hcl` and initialize with `terraform init -backend-config=backend.hcl`.

Apply the resource group and environment targets first, then run a complete
apply to create the bootstrap app. Point the custom-domain DNS record at the app
FQDN, add the hostname, and create the managed certificate. After the
certificate reaches `Succeeded`, bind it explicitly:

```bash
az containerapp hostname bind \
  --resource-group halligalli-container-apps \
  --name halligalli-live-demo \
  --hostname play.halligalli.games \
  --environment halligalli-live-demo \
  --certificate play-halligalli-games
```

Keep the backend config and `terraform.tfvars` local; neither contains
application secrets, but both identify the Azure account.

## Promotion and deployment

Run `Target Promotion - Container Apps` manually with a formal Release Tag. It downloads `paired-release-manifest.json`, verifies the tag/commit/Web/API binding and GitHub provenance for each digest, and creates or updates a Draft PR changing only `deployment/container-apps/desired-state.json`. Development Images are rejected by construction.

The checked-in `v0.7.2` values are a non-deployable historical bootstrap reference (`deploymentEnabled: false`) because that release predates the Paired Release Manifest filename. The first successful target promotion must select a formal release that publishes the renamed manifest; promotion sets `deploymentEnabled: true`. The operator script validates this before any app mutation, so the bootstrap placeholder cannot be deployed.

After merge to `main`, deploy from a trusted local checkout using the operator's interactive Azure CLI session:

```bash
az login
az account set --subscription '<target subscription name or ID>'
./scripts/deploy-container-apps.sh
```

The script verifies the selected resource group and app, renders a candidate revision, records the current 100% traffic revision, deploys the candidate, checks `/internal/identity`, external HTTPS, and a WebSocket upgrade through the candidate FQDN, then switches traffic. Failure restores the previous verified revision.

This repository does not store `AZURE_CREDENTIALS`, a user refresh token, a service-principal secret, or a publish profile in GitHub. Interactive login keeps MFA and deployment authority with the operator. It is intentionally a manual control, not unattended CD. If the tenant later permits a workload identity, automation can be proposed separately without changing the promotion boundary.

## Monitoring and readiness

`Monitor Live Demo` runs a read-only public HTTPS and WebSocket uptime check
daily at 06:17 UTC and may also be dispatched manually. Either check failing
fails the workflow directly; the repository does not create or maintain a
GitHub Issue incident for uptime failures.

The daily check is a basic public availability signal, not a deployment gate.
Platform readiness determines whether a revision may receive traffic, and the
operator runs the same read-only public smoke immediately after an approved
deployment apply. That immediate post-apply smoke establishes deployment
completion without waiting for the next daily uptime run.

No command in this runbook authorizes Azure, DNS, or GitHub Environment mutation. Bootstrap and live recovery require separate explicit approval.
