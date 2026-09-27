# Simulated Player Traffic Report

- Target: approved-live-demo
- Started: 2026-09-27T12:45:53.704Z
- Duration: 729.85 s (maximum 1,200 s)
- Release Tag: v0.10.0
- Web digest: sha256:0536f2cff4b8176e1c3546ae6cf9c3fd0171162edd688ceebbf672fc1430f774
- API digest: sha256:4866bb53cb00ae564f13acbcbb9272580a6eeebb88492a67655c443edefe894a
- Capacity knee: ramp-15-rooms
- Design Load verdict: fail
- Design Load median API CPU: n/a
- Latency signals disagree: no
- Fan-out work triggered (pre-registered rule): undetermined
- Abort reason: server p95 tick lateness exceeded 250 ms
- Client error rate: 0.00% (0/2031)
- Client error reasons: none

## Steps

| Step | Target / peak rooms | Rooms started | Client cadence p95 lateness | Server tick p95 | Command p95 | Due processing p95 | Bell outcomes (correct / wrong / stale / missed) | Redis maxmemory ratio |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ramp-1-rooms | 1 / 1 | 3 | 48.7 ms | 73 ms | n/a | n/a | 30 / 7 / 0 / 7 | 0.78% |
| ramp-2-rooms | 2 / 2 | 3 | 44.8 ms | 71 ms | n/a | n/a | 57 / 11 / 0 / 14 | 0.79% |
| ramp-5-rooms | 5 / 5 | 8 | 75.9 ms | 93 ms | n/a | n/a | 128 / 47 / 0 / 15 | 0.84% |
| ramp-10-rooms | 10 / 10 | 20 | 88 ms | 108 ms | n/a | n/a | 281 / 64 / 0 / 41 | 0.91% |
| ramp-15-rooms | 15 / 15 | 6 | 113.6 ms | 264 ms | n/a | n/a | 21 / 2 / 0 / 6 | 0.93% |

## Room shapes

| Step | Humans per room | Table seats | Difficulty | Invalid shapes |
|---|---|---|---|---:|
| ramp-1-rooms | {"2":0,"3":1,"4":1,"5":1,"6":0} | {"4":0,"5":1,"6":0,"7":0,"8":2} | {"easy":1,"normal":1,"hard":1} | 0 |
| ramp-2-rooms | {"2":0,"3":1,"4":1,"5":1,"6":0} | {"4":0,"5":0,"6":1,"7":1,"8":1} | {"easy":1,"normal":1,"hard":1} | 0 |
| ramp-5-rooms | {"2":1,"3":4,"4":3,"5":0,"6":0} | {"4":2,"5":3,"6":1,"7":1,"8":1} | {"easy":3,"normal":3,"hard":2} | 0 |
| ramp-10-rooms | {"2":6,"3":3,"4":3,"5":3,"6":5} | {"4":1,"5":3,"6":6,"7":4,"8":6} | {"easy":6,"normal":13,"hard":1} | 0 |
| ramp-15-rooms | {"2":0,"3":1,"4":2,"5":2,"6":1} | {"4":1,"5":1,"6":1,"7":0,"8":3} | {"easy":1,"normal":3,"hard":2} | 0 |

## Invariants

| Invariant | Result | Evidence |
|---|---|---|
| at most one correct bell per Bell Window | pass | {"correctHits":517,"source":"in-flight score snapshots","windowsOpened":602,"finalMatches":39} |
| Stale Bells change no score | pass | {"staleFrames":681} |
| Score Breakdown sums to score | pass | {"finalParticipantsChecked":140} |
| room revision monotonic per socket | pass | {"socketLifecycles":157} |
| room sizes stay within 2-6 humans and 4-8 seats without overfilling | pass | {"roomsCreated":40,"invalidRoomShapes":0} |
| Design Load uses ten four-human normal rooms | not_run | {"step":"not reached"} |

## Traffic summary

- Matches completed: 39
- Observed Bell Windows: 602
- Racing bell attempts: 1204
- Planned missed windows: 84
- Accidental wrong bell attempts: 131
- Reconnects: 2
- Intended reaction median: 445 ms
