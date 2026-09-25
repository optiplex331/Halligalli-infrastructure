# K3s Deployment Target

K3s is a single-node Deployment Target on the existing shared Linux host.
The cluster also runs an LLM service. Halligalli owns only its three
namespaces (`halligalli`, `halligalli-observability`, `halligalli-edge`), the
`halligalli-k3s` AppProject and its three Applications, the Cloudflare Tunnel
resources, the operation-time Secrets, and sanitized evidence. It must not
change the host, the K3s installation, the shared K3s add-ons, the shared
Argo CD installation, or the LLM workload.

Every step below that talks to the host, the cluster, Cloudflare, or Terraform
state is an operator-run operation that needs explicit local approval. Static
validation in the README does not authorize or prove a deployment.

## Prerequisites

The host owner provides these before Halligalli is deployed:

- a Ready single-node K3s cluster with its default add-ons;
- a shared Argo CD installation in the `argocd` namespace that can pull the
  public Infrastructure repository;
- SSH access from the operator machine to the host;
- the comma-separated list of LLM namespaces that Halligalli must not touch.

The operator machine needs `kubectl`, `ssh`, `curl`, `python3`, `terraform`,
and `openssl`, plus a Terraform backend and a scoped Cloudflare token for the
Tunnel.

## Access

The Kubernetes API is not a public application route. The operator forwards
local port `16443` over SSH to the host-local K3s API on port `6443` and uses
a context in their own kubeconfig (`KUBECONFIG` or `~/.kube/config`) whose
cluster server is `https://127.0.0.1:16443`. The scripts select that context
with `--context`; they never copy, write, or print kubeconfig contents, and
they do not change the current context. Adding the context to the operator's
kubeconfig is the operator's own one-time setup; keep it out of this
repository, CI, and shared notes.

Set the host-owned values in the ignored operator file:

```bash
cp targets/k3s/operator.env.example targets/k3s/operator.env
# Fill in the context, SSH target, and protected LLM namespace inventory.
```

Keep the API forward open in its own terminal. It exits when the SSH session
is lost:

```bash
targets/k3s/scripts/k3s-access.sh port-forward
```

In the working terminal, load the operator values so the commands below can
use the context, then confirm that the context reaches the API only through a
loopback address:

```bash
set -a; source targets/k3s/operator.env; set +a
targets/k3s/scripts/k3s-access.sh check
```

## Preflight

```bash
targets/k3s/scripts/k3s-preflight.sh
```

The preflight is read-only. It checks the local tools, the loopback context,
the Kubernetes server version, Ready node count, the shared Argo CD namespace
and CRDs, permission to create Applications, the protected LLM namespace
inventory (which must exist and must not overlap a Halligalli namespace),
whether the Halligalli namespaces already exist, and free disk at the K3s data
path. It does not install or upgrade K3s or Argo CD, apply resources, change
add-ons, restart workloads, or touch the LLM service. Stop if it fails.

## First deployment

The Applications track `main`, so the deployed Web/API pair is the one in
`targets/k3s/gitops/runtime/values/experiment.values.json` on `main`.

1. Create the Halligalli namespaces. Creating them here keeps the AppProject
   free of cluster-scoped permissions; the Applications' `CreateNamespace`
   option then finds them present.

   ```bash
   for namespace in halligalli halligalli-observability halligalli-edge; do
     kubectl --context "$HALLIGALLI_K3S_CONTEXT" create namespace "$namespace" \
       --dry-run=client -o yaml |
       kubectl --context "$HALLIGALLI_K3S_CONTEXT" apply -f -
   done
   ```

2. Create the operation-time Redis Secret. The script generates a random
   password, never prints it, and leaves an existing Secret unchanged:

   ```bash
   HALLIGALLI_OPERATION_APPROVED=1 targets/k3s/scripts/apply-redis-auth-secret.sh
   ```

3. Create the Cloudflare Tunnel with Terraform (see
   [Cloudflare Tunnel boundary](#cloudflare-tunnel-boundary)). The
   `halligalli-k3s` HCP Terraform workspace uses remote execution: plans and
   applies run in HCP, the Cloudflare account, zone, and scoped token are
   workspace variables (the token is sensitive), and a local saved plan file is
   not supported. Review the remote plan and confirm the apply only after
   explicit approval:

   ```bash
   terraform -chdir=targets/k3s/terraform init -backend-config=backend.hcl
   terraform -chdir=targets/k3s/terraform plan
   terraform -chdir=targets/k3s/terraform apply
   ```

4. Create the operation-time Tunnel Secret from the sensitive Terraform
   output. `HALLIGALLI_OPERATION_APPROVED=1` must be set in the ignored
   `local-operation.env`:

   ```bash
   targets/k3s/scripts/apply-tunnel-secret.sh
   ```

5. Apply the AppProject, then the three Applications:

   ```bash
   kubectl --context "$HALLIGALLI_K3S_CONTEXT" apply \
     -f targets/k3s/gitops/applications/halligalli-k3s.project.yaml
   kubectl --context "$HALLIGALLI_K3S_CONTEXT" apply \
     -f targets/k3s/gitops/applications/halligalli-k3s-runtime.application.yaml \
     -f targets/k3s/gitops/applications/halligalli-k3s-observability.application.yaml \
     -f targets/k3s/gitops/applications/halligalli-k3s-edge.application.yaml
   ```

6. Wait until all three Applications are `Synced` and `Healthy`:

   ```bash
   kubectl --context "$HALLIGALLI_K3S_CONTEXT" -n argocd get \
     applications.argoproj.io halligalli-k3s-runtime \
     halligalli-k3s-observability halligalli-k3s-edge
   ```

Then run the checks below.

## Checks

The internal runtime smoke port-forwards the Web and API Services, checks
readiness, both release identities, and API metrics, and creates one ephemeral
test room through the Web proxy. It prints the Web/API identities and does not
print or save the room credential:

```bash
targets/k3s/scripts/k3s-runtime-smoke.sh
```

Prove that every Ready Web/API Pod runs the digest pair selected in Git:

```bash
python3 .github/utils/verify_running_pod_digests.py \
  --context "$HALLIGALLI_K3S_CONTEXT" \
  --namespace halligalli \
  --values targets/k3s/gitops/runtime/values/experiment.values.json
```

The public smoke is the only public-route check. It verifies HTTPS, the REST
proxy, and a WebSocket handshake through the Tunnel:

```bash
targets/k3s/scripts/k3s-public-smoke.sh
```

## Promotion and rollback

`Target Promotion - K3s` validates the Product repository's schema-V2 Paired
Release Manifest and artifact provenance, then proposes a Draft PR changing
only `targets/k3s/gitops/runtime/values/experiment.values.json`. It always
updates the Web/API digest pair together. Development Images, mutable tags,
and one-image selections are not eligible. After the PR is merged, Argo CD
reconciles it; run the three checks above.

Rollback is a reviewed Git revert, never a live change. Revert the promotion
commit in a pull request so the same values file returns to the previously
accepted complete Web/API pair:

```bash
git switch -c revert/k3s-<release> origin/main
git revert <promotion-commit>
```

After the revert PR is merged and the runtime Application is `Synced` and
`Healthy`, run the three checks above. Do not use `kubectl set image`,
`kubectl rollout undo`, or an independent Web or API rollback; Argo CD
self-heal would undo them.

## Evidence to hand back

After a deployment, promotion, or rollback, save the following to ignored
local state (for example `.local/k3s/evidence/`) and hand it back so it can be
committed later as sanitized K3s evidence:

- the UTC date and the operation (first deployment, promotion, or rollback);
- the Infrastructure commit on `main` (`git rev-parse origin/main`) and the
  Web/API digests in `experiment.values.json`;
- the full `k3s-preflight.sh` output;
- the `Synced`/`Healthy` status table of the three Applications from step 6;
- the success line of `verify_running_pod_digests.py`;
- the `k3s-runtime-smoke.sh` output, including the Web and API identities;
- the `k3s-public-smoke.sh` output;
- any failed step, with its error message and what was done about it.

Do not include kubeconfigs, non-loopback API server addresses, SSH targets,
node names, IP addresses, private host names, tokens, Secret values,
Terraform plans or state, room codes, or raw `kubectl describe` or log dumps.
Review every line before handing it back.

## Removing Halligalli

Removal is an approved operation that touches only Halligalli resources.
Delete the three Applications and the AppProject, then the three Halligalli
namespaces. The Applications have no resource finalizer, so deleting the
namespaces removes the workloads and the operation-time Secrets. Destroying
the Cloudflare Tunnel is a separate, reviewed Terraform operation.

## Observability boundary

The independent observability target runs one Prometheus, one OpenTelemetry
Collector, and one Tempo Pod in `halligalli-observability`. Prometheus scrapes
`halligalli-api:80/internal/metrics`; the API sends OTLP HTTP traces to the
Collector, which forwards them to Tempo. Prometheus and Tempo retain data in
`emptyDir` storage with no PVC or external monitoring database; the data is
ephemeral and is lost when the Pod or host is replaced. The Services are
ClusterIP-only and have no public route.

During an approved local check, access them only through port-forwarding:

```bash
kubectl --context "$HALLIGALLI_K3S_CONTEXT" -n halligalli-observability \
  port-forward service/halligalli-observability-prometheus 19090:9090
kubectl --context "$HALLIGALLI_K3S_CONTEXT" -n halligalli-observability \
  port-forward service/halligalli-observability-tempo 13200:3200
```

## Shared Argo CD boundary

The target reuses the existing Argo CD installation. The files under
`targets/k3s/gitops/applications/` define one `halligalli-k3s` AppProject and
three separate Applications: runtime, observability, and edge. The Project
accepts only the Infrastructure repository, permits destinations in
`halligalli`, `halligalli-observability`, and `halligalli-edge`, and permits
only the Namespace cluster-scoped resource that `CreateNamespace=true` needs.
All three Applications enable prune and self-heal for their own
namespace-scoped charts.

Secret values are not part of the charts, Application manifests, or Git
history; the Redis and Tunnel Secrets are created at operation time, so Argo
CD neither renders nor prunes them. Never add an LLM namespace or a shared K3s
add-on to this Project.

## Cloudflare Tunnel boundary

Terraform owns the remotely managed Tunnel, the `k3s.halligalli.games`
hostname route, and its proxied CNAME. The only origin in the Tunnel config is
the internal `halligalli-web:80` ClusterIP service. No Kubernetes Ingress,
public TLS resource, API route, Argo CD route, Prometheus route, or Tempo route
is created.

Keep the Terraform backend and operation approval file local:

```bash
cp targets/k3s/terraform/backend.hcl.example targets/k3s/terraform/backend.hcl
cp targets/k3s/terraform/local-operation.env.example targets/k3s/terraform/local-operation.env
```

The remote plan must be reviewed before the apply is confirmed. The backend
file and any run output with state references stay outside Git; Cloudflare
inputs live only as HCP workspace variables.
The Terraform token output is sensitive and belongs only in protected state
and the operation-time Tunnel Secret.

The edge chart runs `cloudflared` in `halligalli-edge` with two replicas in the
experiment profile and one in minimal. It has no Service; both replicas make
outbound Tunnel connections and route only to `halligalli-web:80`.

## Approved experiment flow

Run this flow only with explicit local approval for each disruptive Kubernetes
or host operation. Keep command output, room codes, credentials, and raw
cluster details in ignored local state; do not copy them into Git or shared
notes.

1. Record the reviewed profile, current Web/API/Redis and `cloudflared` Pod
   images, replica counts, Argo Application health, and the internal/public
   smoke results.
2. Delete one Web Pod and one API Pod, wait for replacement, and repeat the
   internal runtime smoke. Scale Web/API from 1 to 2 and back to 1, checking
   Service routing after each change.
3. Trigger a RollingUpdate with a temporary Pod-template annotation, then wait
   for `kubectl rollout status`. Do not change an image with `kubectl set image`.
4. Delete one `cloudflared` Pod, wait for a replacement, and run the public
   smoke. The Tunnel definition and DNS record must remain unchanged.
5. Create an ephemeral room, replace the Redis Pod, and confirm the old room
   is gone while a new room can be created. This is the expected Redis loss
   semantics, not a recovery guarantee.
6. Add harmless live drift to a runtime Deployment, wait for Argo CD self-heal,
   and confirm the reviewed replica/image state is restored. Remove the test
   drift only through the reconciler or the approved desired state.

Useful checks for the approved run, each with
`--context "$HALLIGALLI_K3S_CONTEXT"`, are:

```bash
kubectl -n halligalli get deploy,pods,svc -o wide
kubectl -n halligalli rollout status deployment/halligalli-web
kubectl -n halligalli rollout status deployment/halligalli-api
kubectl -n halligalli-edge rollout status deployment/halligalli-cloudflared
kubectl -n argocd get applications.argoproj.io halligalli-k3s-runtime \
  halligalli-k3s-observability halligalli-k3s-edge
```

The Kubernetes API, Argo CD, Prometheus, and Tempo remain accessible only
through the SSH port-forward or another approved local access path.

## Host restart and rebuild

This target has one K3s node and makes no node-level high-availability claim.
Host shutdown or restart interrupts Halligalli, observability, Argo CD, and
the shared LLM service. K3s uses its embedded SQLite datastore with no backup
commitment. Redis room state is ephemeral and is lost after Redis or host
loss. There is no fixed RTO.

After an approved restart, restore the SSH port-forward, run the preflight,
wait for the shared add-ons and Argo CD, and repeat the checks. No step
exposes Kubernetes API port `6443` publicly.

A rebuild is an approved operator procedure, not an automatic recovery
promise. The host owner first restores the host, K3s, the shared add-ons, and
Argo CD. Halligalli then needs the protected Terraform backend and Cloudflare
state, new operation-time Redis and Tunnel Secrets, and the reviewed
Infrastructure commit; repeat [First deployment](#first-deployment) from the
preflight. A rebuild does not recover Redis rooms or historical traces.
