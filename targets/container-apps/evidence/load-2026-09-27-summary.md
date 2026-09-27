# Live Demo load runs, 2026-09-27

Simulated player traffic against the Live Demo Environment running Release Tag `v0.10.0`
(Web `sha256:0536f2cff4b8176e1c3546ae6cf9c3fd0171162edd688ceebbf672fc1430f774`,
API `sha256:4866bb53cb00ae564f13acbcbb9272580a6eeebb88492a67655c443edefe894a`):
one API replica limited to 0.26 cores, Redis `maxmemory` 180 MB. The Product harness
`tests/load/harness.mjs` generated the traffic from a separate Linux host, not the operator
workstation. API `runtime_summary` lines came from the approved Container Apps log stream,
read as two sessions started five minutes apart and deduplicated by summary timestamp,
because one session ends after about ten minutes.

## Runs

| Run | Ramp (rooms) | Result | Client errors | Invariants |
|---|---|---|---|---|
| [registered](load-2026-09-27-registered.md) | 1, 2, 5, 10, 15, then Design Load | Aborted about 10 s into ramp-15: server p95 tick lateness 264 ms | 0 / 2,031 | 5 pass, Design Load shape not run |
| [probe 1](load-2026-09-27-probe-1.md) | 6, 8, 10, 12, 14, 16 (`--ramp`) | Completed, 16 rooms at step p95 215 ms | 0 / 7,030 | 5 pass over 159 matches |
| [probe 2](load-2026-09-27-probe-2.md) | 8, 11, 14, 16, 18, 20, 22 (`--ramp`, 150 s steps) | Aborted about 100 s into ramp-16: 288 ms | 0 / 3,816 | 5 pass |

Earlier attempts that day aborted because the log stream stopped delivering summaries, not
because of the runtime: terminal handling, an expired Azure CLI login, and a ten-minute
session end during ramp-10. They are not evidence.

## Capacity

- Up to about 12 mixed rooms (45 to 55 sockets), step p95 tick lateness stays between
  100 and 120 ms, with single 15 s windows reaching 165 ms.
- At 14 rooms, windows exceed 150 ms intermittently (step p95 157 to 162 ms).
- At 16 rooms (about 70 sockets), windows run 120 to 290 ms. One probe held for 180 s,
  the other crossed the 250 ms abort. This is the practical ceiling of one replica.
- Adding five rooms at once on top of ten crossed 250 ms in the first window, while
  adding two at a time did not until 16. Simultaneous room starts matter as much as the
  steady count.
- API CPU at the ceiling was 0.16 to 0.18 cores (62 to 69% of the limit) and Redis used
  under 2% of `maxmemory`. Redis `WATCH` retries rose to 60 to 77 per 15 s in the worst
  windows. The limit is latency in the serial due sweep, not CPU or memory.

## Pre-registered decision inputs

The registered run aborted at ramp-15 before its Design Load step, so the harness verdict is
`fail` and the fan-out rule is formally undetermined. The closest measurements are the
10 and 12 room probe steps: p95 105 to 120 ms with isolated windows above 150 ms and CPU
near 40% of the limit. The Design Load of ten rooms therefore sits about 1.6 times below
the observed ceiling.

## Caveats

- Rooms mix 2 to 6 humans, 4 to 8 seats, and all difficulties; they are not the Design
  Load shape of ten four-human normal rooms.
- `at` in each result's `runtimeSummary` is when the harness received the line, and
  arrivals are bursty; the API emitted summaries on a steady 15 s cadence.
- `activeRooms` counts rooms not yet expired in Redis, including idle lobby rooms, so it
  runs well above the harness's concurrent rooms. Idle rooms are not due-processed.
- No room creation was refused by the hourly per-address budget.
