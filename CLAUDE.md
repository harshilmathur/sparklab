# SparkLab — instructions for AI agents working in this repo

This is a measurement repo: a benchmark harness, raw results, and distilled
findings for DeepSeek-V4-Flash serving on NVIDIA DGX Spark (GB10). It is not
a serving recipe (see README credits for those).

## Hard rules (the methodology — keep it honest)

- Every benchmark claim needs its CSV in `bench/results/`, an engine tag,
  and >= 3 repeats (report MEDIANS) for record claims. Label smoke runs.
- Token counts come from the server's `usage` field only — never count SSE
  chunks or tokenize client-side.
- Never compare tok/s across engines unless both used usage accounting —
  and never compare closed-loop fixed-window aggregates (this harness) with
  server-side decode-window rates (most community numbers): same hardware
  reads ~2.5x apart on the two rulers.
- Warm the server before any prefill measurement (first-touch runs are
  30-60% slow from shape compilation).
- Bench speculation on BOTH corpora (`draftable` and `adversarial`) — one
  number lies.
- Run `python3 bench/test_agent_bench.py` after any harness change.
- Every version pin lives in `pins.env`; docs must not restate versions.

## Layout

- `bench/agent_bench.py` — the harness (stdlib-only; see README for usage)
- `bench/workloads/` — the two corpora
- `bench/results/` — every raw CSV behind every published claim
- `docs/RESULTS-LOG.md` — the dated log, newest first (records AND failures)
- `docs/LAWS.md` — distilled operational/performance laws; read before
  touching GB10 hardware (kernel pin, AC-cycle, UVM, cold-start rules)
