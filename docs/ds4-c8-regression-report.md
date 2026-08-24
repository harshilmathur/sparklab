# C8 batch throughput regresses ~18-29% from v0.5.6 to v0.5.6.1+ on CUDA/GB10 — bisected to the Metal DSpark merge

**Setup:** DGX Spark (GB10, sm_121a, CUDA 13.0), `make cuda-spark`, DeepSeek-V4-Flash-0731
IQ2XXS + DSpark drafter, ship config + `DS4_BATCH_VMM_BUDGET_MB=12288`, ctx 32768.
Benchmark: closed-loop fixed 180 s windows, usage-field token accounting, 8 concurrent
sessions, draftable (tool-call/JSON/code) corpus, 3 repeats per point.

**Symptom:** C8 aggregate drops from **55.1 tok/s (v0.5.6) to 45.3 (v0.5.6.3)**, −17.8%
(adversarial corpus: 58.6 → 47.0, −19.8%). C1 is unaffected (+3%). The number is eerily
stable — 45.3 ±0.3 across every config I tried.

**Ruled out before bisecting:**
- the v0.5.6.3 capacity-tether pool size (relaunched with `DS4_BATCH_VMM_BUDGET_MB=12288`,
  boot line confirms `budget=12.00 GiB` — identical 45.3)
- the new seat-shed hold (`DS4_CONT_HOLD_SHED_S=0` — identical 45.4)

**Bisect (C8 draftable, one point per commit):**

| commit | C8 agg tok/s | reading |
|---|---|---|
| v0.5.6 | 55.1 | baseline |
| 3375a6d Merge PR #2 (Metal DSpark drafter) | **39.1** | **regression origin, −29%** |
| f9253ba +CUDA signature mirror amendment | 39.4 | no change |
| 871ae69 +seat-shed hold | 45.5 | partially masks it (+6) |
| v0.5.6.2 / v0.5.6.3 | 45.3 | steady |

So the Metal drafter merge costs CUDA batch decoding ~29% through shared-path changes,
and the seat-shed commit added right after happens to mask a third of the loss —
which makes the remaining regression easy to misattribute to later commits (I initially
suspected the v0.5.6.3 re-tether; it's innocent, and its capacity-tether works as
designed).

**Update — v0.6.3 tested (2026-08-24):** the regression is not fixed and
concurrency got dramatically worse: at 8-way the drafter is gated off
entirely (`CONT_MTP_ACCEPT ... drafts=0 hits=0 accept=0.0%`,
`CONT_MTP_DRAFTGATE ... concgate=1907`) and per-stream decode collapses to
~6 tok/s (requests finish by length at ~40 s / 236 tokens). Single-request
serving looks normal. Tested on kernel 6.17.0-1029 with clean memory
reclaim, so this is the engine, not our host (we did separately find and
pin around an unrelated 6.17.0-1031 kernel issue).

Happy to share raw CSVs / rerun candidates. For now we've pinned v0.5.6 as the fast
CUDA configuration.
