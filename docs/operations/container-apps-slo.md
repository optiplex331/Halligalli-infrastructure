# Container Apps Live Demo service targets

These are targets for the `container-apps` Live Demo Environment, derived from measured
load runs plus a margin. They are not commitments: the Live Demo has no real players, no
support obligation, and no alerting or paging. Nothing in this document creates an alert
rule. The [runbook](container-apps.md) owns deployment, rollback, and monitoring.

The targets apply to the runtime shape in Terraform (one API replica limited to 0.26 cores,
Redis inside the replica with `maxmemory` 180 MB) and to Release Tag `v0.10.1` or later.
A change to that shape, or a release that changes the due sweep or publishing, needs new
measurements before these numbers apply again.

## Data source

The API prints one `runtime_summary` line to stdout every 15 seconds. Each 15 s window is
one sample: tick lateness p95, API CPU cores, Redis used memory, `WATCH` retries, active
rooms, and active sockets. Read it through an approved Container Apps log stream; the
internal metrics endpoint is not public. Client error rate comes from the load harness,
because the API does not count client-visible errors per window.

Evidence: [`v0.10.1` load runs](../../targets/container-apps/evidence/load-2026-09-27-v0.10.1-summary.md),
compared with the [`v0.10.0` runs](../../targets/container-apps/evidence/load-2026-09-27-summary.md).

## Targets

| Measure | Target | Measured on `v0.10.1` | Margin |
|---|---|---|---|
| Tick lateness p95 per 15 s window | at most 150 ms | at most 103 ms in all 140 windows, up to 16 rooms | 47 ms; the 100 ms due-sweep cadence is the floor |
| Supported concurrent rooms | 12 mixed rooms (about 50 sockets) | 16 mixed rooms (about 78 sockets) without a window above 103 ms | 25% below the highest measured load |
| Design Load (10 rooms of four humans, normal) | holds | step p95 101 ms, median API CPU 21.5% of the limit | inside the room target |
| Client error rate per run | below 1% | 0 of 11,110 operations | the harness aborts at 2% |

Supporting bounds that stayed far from their limits: Redis used at most 1.4% of `maxmemory`
(the harness aborts at 80%), and API CPU peaked at 0.11 cores, 41% of the limit.

The supported room count is set below the highest measured load, not at a knee: no step
crossed 150 ms, so the actual ceiling was not found. On `v0.10.0` the same traffic crossed
150 ms at 14 to 16 rooms, and five simultaneous room starts on top of ten crossed 250 ms,
so bursts of room starts are the first thing to watch if load approaches the target.

## Known limitations

### Room loss on deploy

Every deployment, including a rollback, loses all active rooms. Redis runs inside the
Container App replica and is replaced with it, so no drain or reconnect can preserve room
state. A deployment is therefore a planned outage for every open room. The Web's
reconnect after a planned API restart (close code 1012) preserves rooms only on `k3s` and
`aks`, where Redis runs outside the API replica. Moving Redis out of the replica is out of
scope for this target.

### Missed Bell Windows after an outage

When the API stops while a Bell Window is open, the window expires unobserved. On catch-up,
the due sweep charges that one window as missed and flips the next card with a deadline
counted from the current time, so the next window gets its full length. An outage of any
length therefore charges at most one missed Bell Window per room. This is intended
behavior, not a defect.

## Reviewing the targets

Rerun the registered ramp and the capacity probe from the load harness (Product
`tests/load/README.md`) after any release that changes the due sweep, publishing, or the
runtime shape, and update this document from the new evidence. Every run against the Live
Demo needs explicit approval.
