# K3s Deployment Target

K3s is a single-node Deployment Target on the existing shared Linux host.
The cluster also runs an LLM service. Halligalli must stay inside its own
namespaces and must not change the host-owned K3s add-ons or the LLM workload.

## Access boundary

The Kubernetes API is not a public application route. The local operator uses
the host's SSH access and forwards local port `16443` to the host-local K3s
API on port `6443`. The copied admin kubeconfig is stored only under ignored
local state. It must never be committed, sent to CI, printed, or included in
shared notes.

Set the host-owned values in an ignored file:

```bash
cp targets/k3s/operator.env.example targets/k3s/operator.env
# Fill in the SSH target and the explicit protected LLM namespace inventory.
```

Use three local terminals for the operator path:

```bash
targets/k3s/scripts/k3s-operator.sh sync-kubeconfig
targets/k3s/scripts/k3s-operator.sh port-forward
targets/k3s/scripts/k3s-operator.sh preflight
```

`sync-kubeconfig` performs one read-only SSH copy and rewrites the copied API
endpoint to `127.0.0.1:<local-port>`. `port-forward` stays attached to the
SSH session and exits if that session is lost. `preflight` records the K3s
version, Argo CD namespace state, `kube-system` add-ons, the explicit LLM
namespace inventory, node capacity, and free disk at the K3s data path under
ignored `.local/k3s/` state.

The preflight also checks that the configured public origin is HTTPS and does
not select port `6443`. Public application routing belongs to the later
Cloudflare Tunnel target; the Kubernetes API remains local through SSH.

After the runtime has been reconciled, an approved local smoke can verify the
internal Web/API/Redis path without changing the AKS target:

```bash
targets/k3s/scripts/k3s-runtime-smoke.sh
```

The smoke uses local service port-forwards, checks Web and API health surfaces,
and creates one ephemeral test room through the Web proxy. It does not expose
or save the response credential.

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
kubectl -n halligalli-observability port-forward \
  service/halligalli-observability-prometheus 19090:9090
kubectl -n halligalli-observability port-forward \
  service/halligalli-observability-tempo 13200:3200
```

## Shared Argo CD boundary

The target reuses the existing Argo CD installation. The files under
`targets/k3s/gitops/applications/` define one `halligalli-k3s` AppProject and
separate runtime and observability Applications. The Project accepts only the
Infrastructure repository, permits destinations in `halligalli`,
`halligalli-observability`, and `halligalli-edge`, and permits no cluster-scoped
resources. Both Applications enable prune and self-heal for their own
namespace-scoped charts.

Create the operation-time Redis Secret before the runtime Application is first
reconciled. Secret values are not part of the chart, Application manifests, or
Git history. The later Tunnel Secret follows the same boundary. Never add the
LLM namespace or shared K3s add-ons to this Project.

## Cloudflare Tunnel boundary

Terraform owns the remotely managed Tunnel, the `k3s.halligalli.games`
hostname route, and its proxied CNAME. The only origin in the Tunnel config is
the internal `halligalli-web:80` ClusterIP service. No Kubernetes Ingress,
public TLS resource, API route, Argo CD route, Prometheus route, or Tempo route
is created.

Keep the Terraform backend and Cloudflare operation file local:

```bash
cp targets/k3s/terraform/backend.hcl.example targets/k3s/terraform/backend.hcl
cp targets/k3s/terraform/local-operation.env.example targets/k3s/terraform/local-operation.env
terraform -chdir=targets/k3s/terraform init -backend-config=backend.hcl
terraform -chdir=targets/k3s/terraform plan -out=k3s-cloudflare.tfplan
terraform -chdir=targets/k3s/terraform show k3s-cloudflare.tfplan
```

The plan must be reviewed before a separate, explicitly approved apply. The
plan and backend may contain sensitive state references and stay outside Git.

The Terraform token output is sensitive and belongs only in protected state.
After an approved Terraform apply, create the operation-time Kubernetes Secret
and then let the edge Application reconcile:

```bash
targets/k3s/scripts/apply-tunnel-secret.sh
```

The edge chart runs `cloudflared` in `halligalli-edge` with two replicas in the
experiment profile and one in minimal. It has no Service; both replicas make
outbound Tunnel connections and route only to `halligalli-web:80`. The Secret
is external to GitOps, so Argo CD does not render or prune its value.

After Cloudflare and the edge workload are healthy, the read-only public smoke
checks HTTPS, the REST proxy, and a WebSocket handshake:

```bash
targets/k3s/scripts/k3s-public-smoke.sh
```

## Approved experiment flow

Run this flow only with explicit local approval for each disruptive Kubernetes
or host operation. Keep the synced kubeconfig, command output, room codes,
credentials, and raw cluster details in ignored local state; do not copy them
into Git or shared notes.

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

Useful checks for the approved run are:

```bash
kubectl -n halligalli get deploy,pods,svc -o wide
kubectl -n halligalli rollout status deployment/halligalli-web
kubectl -n halligalli rollout status deployment/halligalli-api
kubectl -n halligalli-edge rollout status deployment/halligalli-cloudflared
kubectl -n argocd get applications.argoproj.io halligalli-k3s-runtime \
  halligalli-k3s-observability halligalli-k3s-edge
```

The public smoke is the only public-route check. The Kubernetes API, Argo CD,
Prometheus, and Tempo remain accessible only through the SSH port-forward or
other approved local access path.

## Host restart and rebuild flow

The host owner may verify a planned shutdown and restart only as a separately
approved operation. Before shutdown, record the same bounded status above;
after startup, reconnect through SSH, resync the kubeconfig, restore the local
port-forward, run the read-only preflight, wait for shared add-ons and Argo CD,
and repeat the internal/public smoke. No step exposes Kubernetes API port
`6443` publicly.

A full rebuild starts from these inputs:

- the host and K3s installation procedure, including the reviewed K3s version;
- the shared K3s add-on and Argo CD bootstrap owned by the host operator;
- protected Terraform backend configuration and Cloudflare state;
- operation-time Cloudflare, Redis, and Tunnel Secret values;
- the reviewed Infrastructure commit, K3s Helm values, and Argo Applications.

Restore the host and shared components first, then run the SSH preflight. Next
restore or reconcile the Cloudflare Tunnel, create the operation-time Secrets,
and let Argo CD create the three Halligalli namespaces and reconcile runtime,
observability, and edge. Finish with the internal and public smoke and record
only sanitized results. A rebuild does not recover Redis rooms or historical
traces.

## Paired promotion and rollback

`Target Promotion - K3s` validates the Product repository's schema-V2 Paired
Release Manifest and artifact provenance, then proposes a Draft PR changing
only `targets/k3s/gitops/runtime/values/experiment.values.json`. It always
updates the Web/API digest pair together. Development Images, mutable tags,
and one-image selections are not eligible.

Argo CD reconciles the reviewed desired-state change. Rollback is a reviewed
Git change that restores a previously accepted complete Web/API pair in the
same K3s values file; it does not use `kubectl set image`, `rollout undo`, or
an independent Web/API rollback. After reconciliation, run the internal and
public smoke commands above.

## Protected shared state

The following remain outside Halligalli ownership:

- the existing K3s Traefik, ServiceLB, and local-path-provisioner components;
- the LLM namespaces and their workloads;
- the single-node host and its K3s installation.

The preflight is read-only. It does not install or upgrade K3s or Argo CD,
apply Kubernetes resources, change add-ons, restart workloads, or alter the
LLM service. Any remote mutation requires separate explicit local approval.

## Shutdown, backup, and rebuild boundary

This target has one K3s node and makes no node-level high-availability claim.
Host shutdown or restart interrupts Halligalli, observability, Argo CD, and
the shared LLM service; verify recovery only during an explicitly approved
operation. K3s uses its embedded SQLite datastore with no backup commitment.
Redis room state is ephemeral and is expected to be lost after Redis or host
loss.

A rebuild is an approved operator procedure, not an automatic recovery
promise. It requires the documented host/K3s installation inputs, the shared
Argo CD bootstrap, operation-time Redis and Tunnel Secrets, reviewed
Halligalli desired state, and the public Cloudflare configuration. A rebuild
must restore the shared-host boundary before Halligalli resources are
reconciled. There is no fixed RTO.
