# Game day: k3s rollback during running matches, 2026-09-27

An approved drill on the `k3s` target: roll back from `v0.10.1` to `v0.10.0` through a reviewed
Git revert while simulated players are in running matches, then roll forward the same way.
This is a rehearsal, not an incident.

| Release | Product commit | Web digest | API digest |
|---|---|---|---|
| `v0.10.1` | `e52a90061ef47214bf4960d66c25ad53ef08e4a9` | `sha256:234cc6b4a30e0e782bd9fa04ee42a1d3eea37f70b348fbb90ca9d91373de3a97` | `sha256:7af9f4bda594f2426b72ef6a0f21f3b6020668f95dd94eb756ed32a17f3063fd` |
| `v0.10.0` | `c4d752c8ce0a81fca7315196dd979afee86bdbf6` | `sha256:0536f2cff4b8176e1c3546ae6cf9c3fd0171162edd688ceebbf672fc1430f774` | `sha256:4866bb53cb00ae564f13acbcbb9272580a6eeebb88492a67655c443edefe894a` |

Both releases share the Stale Bell protocol, so clients on either build keep working across
each step.

## Setup

- Runtime: two Web and two API replicas with `RollingUpdate` (`maxSurge` 1, `maxUnavailable` 0),
  one Redis Pod outside the API replicas. Argo CD polls Git with its default interval.
- Traffic: the Product load harness with `--target k3s --ramp 2,3,4,5 --step-seconds 180`
  (12 minutes) from a separate Linux host, through the target's public Cloudflare Tunnel route.
  Bots reconnect after a planned-restart close (1012) like the Web client: 0 to 500 ms of jitter,
  then backoff. Any other close is a client error.
- Observation: API `runtime_summary` lines from every API Pod, Pod lifecycle events, and the
  runtime Application's sync revision and health, all read-only and collected locally.

## Timeline (UTC)

| Time | Event |
|---|---|
| 23:09:14 | Harness starts; runtime Application `Synced`/`Healthy` on `v0.10.1` |
| 23:12:21 | Rollback PR (revert of the `v0.10.1` promotion) merged, 7 s into the three-room step |
| 23:16:10 | Argo CD applies the revert; first `v0.10.0` Web and API Pods created |
| 23:16:13 | Application `Progressing` |
| 23:16:36 | Last `v0.10.1` Pod removed; rollout took 26 s |
| 23:16:39 | Application `Synced`/`Healthy` on `v0.10.0`, 4 min 18 s after the merge |
| 23:21:59 | Harness ends without an abort |
| 23:22:22 | Roll-forward PR (revert of the revert) merged |
| 23:26:03 | Argo CD applies it; `v0.10.1` Pods roll out without traffic |
| 23:26:24 | Application `Synced`/`Healthy` on `v0.10.1` |

Most of the time from merge to rollout is Argo CD's Git polling, not the rollout itself.

## Results

| Measure | Result |
|---|---|
| Planned restart closes (1012) | 16, all during the rollback rollout |
| Reconnects after 1012 | 16 of 16; p50 310 ms, max 1.76 s from close to the first snapshot |
| Rooms in the k3s Redis | Survived: every bot rejoined its room and play continued; active rooms kept rising (14 to 17) across the Pod swap |
| Client errors | 9 of 1,649 operations (0.55%), all in the step that contained the rollout; the other three steps had none |
| Invariants | 5 of 5 pass over 37 completed matches (one correct bell per window, Stale Bells change no score, Score Breakdowns sum, revision monotonic per socket, room shapes) |
| Tick lateness | Every 15 s window from both API replicas at or below 100 ms (102 windows); at most 85 ms in the windows around the Pod swap |
| Bell Windows unraced while bots reconnected | 0 |

The 9 errors were 3 room-entry requests answered with HTTP 502, 4 new WebSocket connections that
failed, and 2 commands sent on a socket that had just closed. All fall in the 26 s rollout.

## Checks

| Git state | Argo CD Applications | Running Pod digests | Internal runtime smoke | Public smoke |
|---|---|---|---|---|
| Rolled back to `v0.10.0` | `Synced`/`Healthy` | pass | pass, identities `0.10.0` | pass |
| Rolled forward to `v0.10.1` | `Synced`/`Healthy` | pass | pass on the second attempt, identities `0.10.1` | pass |

The first runtime smoke after the roll-forward started as the Application turned `Healthy`,
while an old API Pod was still terminating. Its `port-forward` to the API Service bound to that
Pod and failed when the Pod left. Rerun a minute later, when all four Pods were new, it passed.

## Findings

1. A rollback during running matches keeps rooms on k3s: Redis is outside the API replicas,
   the API closes sockets with 1012, and clients that reconnect like the Web client rejoin
   within two seconds.
2. The rollout still produces a short burst of errors for requests that start during it. The
   API Pods have no `preStop` delay, so a terminating Pod stops serving while it can still be
   selected through the Service; three HTTP 502s and four failed connections match that window.
   A short `preStop` sleep before shutdown is the likely fix; it is not changed by this drill.
3. `kubectl port-forward` to a Service binds one Pod, so run the internal runtime smoke only after
   the old Pods are gone, not as soon as the Application reports `Healthy`.
4. Argo CD's polling interval dominates the time to roll back (about four minutes of the
   4 min 18 s). Rollback speed is bounded by Git polling unless a sync is triggered.

## Sanitization

No kubeconfig, API server address, node or host name, room code, credential, or raw log is
included. Raw observations stay in ignored local state.
