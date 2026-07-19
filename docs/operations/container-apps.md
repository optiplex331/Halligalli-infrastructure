# Container Apps Live Demo

`container-apps` is the target for the continuously available Live Demo Environment at `https://play.halligalli.games`. It uses PR-gated desired state plus an explicit local operator deployment, is not GitOps, and has no public API domain. Checked-in desired state and static validation do not prove that a separately approved live deployment has occurred.

## Runtime ownership

One Azure Container App contains separate Web, API, and ephemeral Redis
containers sharing localhost networking. Terraform owns the exact region,
resource names, resource allocations, scaling limits, images, ingress, and
platform probes; do not copy those values into operator notes. The checked-in
Deployment Desired State owns the complete release selection, and the Terraform
root consumes it directly.

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
  --resource-group '<resource group from the reviewed Terraform state>' \
  --name '<Container App from the reviewed Terraform state>' \
  --hostname play.halligalli.games \
  --environment '<Container Apps environment from the reviewed Terraform state>' \
  --certificate '<managed certificate name>'
```

Keep the backend config and `terraform.tfvars` local; neither contains
application secrets, but both identify the Azure account. If an existing
`terraform.tfvars` still declares `web_image`, `api_image`, or `redis_image`,
remove those obsolete entries; release images come only from the checked-in
Deployment Desired State.

## Promotion and deployment

Run `Target Promotion - Container Apps` manually with a formal Release Tag. It downloads `paired-release-manifest.json`, verifies the tag/commit/Web/API binding and GitHub provenance for each digest, and creates or updates a Draft PR changing only `deployment/container-apps/desired-state.json`. Development Images are rejected by construction.

Promotion establishes release trust once. Reviewers decide whether to deploy
the selected Release Tag to the Container Apps target, confirm the target-only
diff, and consider operational blockers without manually repeating manifest,
digest, or provenance checks. A request for the already selected release is a
no-op and does not repeat provenance.

Terraform reads the checked-in desired-state file directly and rejects disabled
deployment or incomplete, mutable, and placeholder Web/API/Redis image
references before apply. Promotion alone establishes the formal Web/API release
binding, target metadata, and artifact provenance; Terraform does not repeat
those checks. Local variable files do not select release images.

After merge to `main`, deploy from a trusted local checkout using the operator's interactive Azure CLI session. Initialize the configured backend, save a plan, and review the exact saved plan before approving apply:

```bash
az login
az account set --subscription '<target subscription name or ID>'
terraform -chdir=terraform/container-apps init -backend-config=backend.hcl
terraform -chdir=terraform/container-apps plan -out=container-apps.tfplan
terraform -chdir=terraform/container-apps show container-apps.tfplan
```

Only after the saved plan has been reviewed and explicitly approved, run the apply and the existing read-only public HTTPS/WebSocket smoke as one operation:

```bash
terraform -chdir=terraform/container-apps apply container-apps.tfplan && python3 .github/utils/external_monitor.py --origin https://play.halligalli.games
```

Do not consider the deployment complete if apply or smoke fails. Terraform is the only command in this procedure that mutates the Container App; the smoke is read-only. The Container App uses Single revision mode, so Azure keeps traffic on the prior ready revision until the complete new revision passes its platform probes.

This repository does not store `AZURE_CREDENTIALS`, a user refresh token, a service-principal secret, or a publish profile in GitHub. Interactive login keeps MFA and deployment authority with the operator. It is intentionally a manual control, not unattended CD. If the tenant later permits a workload identity, automation can be proposed separately without changing the promotion boundary.

## Rollback

Rollback restores a complete previously reviewed Paired Release in source control. Revert the promotion commit that changed `deployment/container-apps/desired-state.json`, review and merge that revert, then create and review a new Terraform plan from the resulting `main`. Apply that saved plan and run the same immediate public smoke command above. The revert must restore release version, commit, Web digest, and API digest together; editing or rolling back only one release image is invalid.

Single revision delivery does not retain manual traffic weights or provide an immediate traffic-flip rollback. If a new revision fails platform readiness, Azure leaves traffic on the previous ready revision. If a revision passes readiness but fails the public smoke, restore the previous complete pair through Git review and another approved Terraform apply.

## Monitoring and readiness

`Monitor Live Demo` runs a read-only public HTTPS and WebSocket uptime check
once daily and may also be dispatched manually. The workflow owns its exact
schedule. Either check failing
fails the workflow directly; the repository does not create or maintain a
GitHub Issue incident for uptime failures.

The daily check is a basic public availability signal, not a deployment gate.
Terraform declares HTTP startup and readiness probes for Web, an API startup
probe plus `/internal/ready` readiness (which checks Redis), and TCP startup and
readiness probes for Redis. Platform readiness determines whether a revision
may receive traffic. The operator then runs the same read-only public smoke
immediately after an approved deployment apply; this establishes external
HTTPS and WebSocket behavior without waiting for the next daily uptime run.

No command in this runbook authorizes Azure, DNS, or GitHub Environment mutation. Bootstrap and live recovery require separate explicit approval.
