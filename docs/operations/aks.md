# AKS Deployment Target

This document is the boundary reference for the maintained `aks` Deployment
Target. The approval-gated validation procedure is
[AKS Validation Procedure](aks-validation.md).

## Current state

Paired Release `v0.7.2` is the last fully deployment-verified AKS baseline from
the approved two-node run on 2026-07-13.
The run demonstrated:

- two Web and two FastAPI replicas across two `Standard_D4ls_v6` nodes;
- same-origin two-seat and six-seat REST/native-WebSocket journeys;
- ephemeral Redis authority and designed room loss after Redis replacement;
- API Pod disruption and non-Redis-node drain/reschedule;
- Argo CD self-heal;
- Prometheus, Grafana, OpenTelemetry Collector, and Tempo evidence;
- paired rollback from `v0.7.2` to `v0.7.1` and restoration to `v0.7.2`.

The reviewed destroy finished after evidence capture. Terraform state is empty,
the proof and node resource groups are absent, local sensitive material was
removed, and no Halligalli workload remains deployed on AKS.

## Ownership

Terraform owns Azure resources through the AKS cluster boundary. Argo CD owns
the runtime and observability Applications rendered from Infrastructure-owned
charts and values. The Product Repo owns Web/API source, Paired Release Tags,
GHCR images, GitHub artifact provenance, and schema-V2 Paired Release Manifests.

Product automation has no Infrastructure write credential. Infrastructure
promotion may open or update one Draft PR but cannot merge it or sync Argo CD.

## Safety gate

Without explicit local-operation approval, do not run:

- a real Terraform plan, apply, or destroy;
- Azure subscription, quota, capacity, or credentialed proof preflight;
- AKS credential retrieval or controller bootstrap;
- Kubernetes or Argo CD apply, sync, drift, disruption, drain, or rollback;
- DNS changes or paired digest selection;
- Redis Secret generation or proof cleanup.

Static Python tests and backendless Terraform validation are separate from live
operation and do not establish a deployed state.

## Historical paths

The June 19, 2026 standalone Node.js/socket.io AKS proof and the earlier
split-origin Static Web Apps plus backend-only Container Apps environment are
historical. The current same-origin Container Apps Live Demo is an independent
target, not an AKS fallback.

## Evidence

The public, sanitized completion summary is
[`evidence/aks-validation-summary.json`](../../evidence/aks-validation-summary.json).
It binds Paired Release `v0.7.2`, immutable dependency digests, the validated
capabilities, and the destroy result. Raw proof output and failed-attempt records
are intentionally excluded from this public repository.
