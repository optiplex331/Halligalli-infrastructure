# Container Apps Live Demo

`container-apps` is the target for the continuously available Live Demo Environment at `https://play.halligalli.games`. It is PR-gated IaC/CD, not GitOps, and has no public API domain. Checked-in desired state and static validation do not prove that the separately approved bootstrap or a live deployment has occurred.

## Runtime and cost target

One Azure Container App contains three separate containers sharing localhost networking:

| Container | Purpose | CPU | Memory |
|---|---|---:|---:|
| Web | nginx public gateway on port 8080 | 0.12 vCPU | 0.25 GiB |
| API | FastAPI on localhost:8000 | 0.26 vCPU | 0.5 GiB |
| Redis | ephemeral Redis on localhost:6379 with persistence disabled | 0.12 vCPU | 0.25 GiB |

The initial app total is 0.5 vCPU / 1 GiB with `minReplicas = 1` and `maxReplicas = 1`. The monthly budget target is USD 25. An approved ephemeral platform test on 2026-07-17 showed that Azure rejects the original `0.125 / 0.25 / 0.125` split because each container CPU value may have at most two decimal places; Azure accepted the nearest symmetric `0.12 / 0.26 / 0.12` split without changing the total.

Terraform binds `play.halligalli.games` to an existing Container Apps environment certificate. Creating the certificate and DNS validation records is a separately approved bootstrap operation; this repository does not hide either behind the deployment workflow.

## Promotion and deployment

Run `Target Promotion - Container Apps` manually with a formal Release Tag. It downloads `paired-release-manifest.json`, verifies the tag/commit/Web/API binding and GitHub provenance for each digest, and creates or updates a Draft PR changing only `deployment/container-apps/desired-state.json`. Development Images are rejected by construction.

The checked-in `v0.7.2` values are a non-deployable historical bootstrap reference (`deploymentEnabled: false`) because that release predates the Paired Release Manifest filename. The first successful target promotion must select a formal release that publishes the renamed manifest; promotion sets `deploymentEnabled: true`. The deployment workflow validates this locally before Azure sign-in, so merging the scaffolding cannot deploy the placeholder.

After merge to `main`, `Deploy Container Apps Live Demo` first validates that desired state is deployable, then uses the protected GitHub Environment `container-apps`. That Environment requires owner review and protected-branch deployment. It must contain:

- secret `AZURE_CREDENTIALS`: service-principal JSON containing a client secret;
- a principal with only the permissions needed to update and inspect the Container App inside resource group `halligalli-container-apps` (resource-group scope, not subscription scope).

The Environment is repository configuration; credential values are never stored in Git.

The workflow renders a candidate revision, records the current 100% traffic revision, deploys the candidate, checks `/internal/identity`, external HTTPS, and a WebSocket upgrade through the candidate FQDN, then switches traffic. Failure restores the previous verified revision and uploads instructions for a Draft desired-state repair PR when merged Git and live state diverge.

## Monitoring and readiness

`Monitor Live Demo` runs external HTTPS and WebSocket checks every ten minutes.
The first failed check opens one GitHub incident; later failures update that open
incident, and the next successful check records recovery and closes it.
Repository Issues must be enabled for notifications; replace or extend that sink
if paging is required. This public monitor is deliberately separate from API
`/internal/ready`, which is an internal readiness surface used during deployment
and diagnosis.

No command in this runbook authorizes Azure, DNS, or GitHub Environment mutation. Bootstrap and live recovery require separate explicit approval.
