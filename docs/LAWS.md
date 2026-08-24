# The Laws — distilled findings from three weeks on GB10

Evidence lives in [RESULTS-LOG.md](RESULTS-LOG.md) with CSVs in `bench/results/`.

## Verified performance laws (RESULTS-LOG.md has the evidence)

- Box record 69.1 tok/s aggregate (llama.cpp, slots=concurrency, spec off).
- TP=2 aggregate record 59.3 @C12 (2026-08-24; C8 is underfed at seqs12 —
  bench TP=2 aggregates at C12; C16 = upstream deadlock trigger, never).
- C1 decode record 65.8 tok/s draftable — TP=2 Mia stack post firmware
  refresh (2026-08-24 audit re-record; adversarial 33.4). K2 single-box
  holds 54.1.
- AC-CYCLE LAW: after ANY QSFP/PCIe hardware change, hard power-cycle
  (cords out) BOTH boxes — stale PCIe/NIC state cost 7.9x NCCL bandwidth
  and half of C1 decode until cycled. Warm reboots do NOT clear it.
- TP=2 launches always carry UCX_MEM_MMAP_HOOK_MODE=none and
  UCX_RCACHE_MAX_UNRELEASED=1024 (RDMA cache leak drains UMA -> wedge).
- eugr b12x build: fp8 KV only (no nvfp4_ds_mla); EP fatal; greedy draft
  no better than probabilistic.
- (prior) C1 single-box record 54.1 tok/s draftable (K2 TUNED config 2026-08-17:
  seqs12, graph captures 1-12, lpt1024, retention4096 — ship config only
  captured graphs to 6, so C8 ran eager; tune fixed C8 TTFT 8.6s->1.5s and
  aggregate 14->21.5). Still a single-stream tool; ds4 stays daily driver.
- vLLM law: CUDAGRAPH_CAPTURE_SIZES must cover every concurrency you run.
- Warm-prefix law: cached-prefix turns at depth cost SECONDS (370K: 8.8 s
  warm vs ~5.5 min cold). Keep session prefixes cached for 1M work.
- 1M context VERIFIED on ONE box (K2, MAX_MODEL_LEN=1000000): needle found
  at 994K tokens; cold-1M prefill ~22 min (735 tok/s at depth).
- Slot law: llama.cpp --parallel MUST equal expected concurrency.
- DSpark speculation: big win at C1 (+40-56%), washes out by C4, slight
  loss at C8-12. ds4 owns TTFT/interactive; llama.cpp owns saturated batch.
- DSpark quality cost: ZERO (A/B verified, identical 79% both arms). But
  on llama.cpp NEVER combine --parallel >1 with speculation: upstream
  #26741 garbles output (KV rollback poisoning). Single-slot spec is safe.
- ds4 sustained-load degradation: ROOT-CAUSED (grow-only per-bank KV pool
  squeezes weights out of page cache). FIX: start with
  `DS4_BATCH_VMM_BUDGET_MB=12288` (pins the pool; daily driver runs it).
- Clock lock is a NO-OP on BOTH decode and prefill (falsified by control
  2026-08-23; GB10 self-caps ~2411-2450). TP=2 warm prefill ~2.6K tok/s
  @32K; first-touch runs are 30-60% slower (shape-compile warmup) — warm
  the server before ANY prefill claim.
- TP=2 boot can wedge (shm_broadcast spin, container stays "up" — false
  proxy). Recovery: recycle both ranks. Mini watchdog AUTO-RECOVERS
  (3 down-ticks -> recycle, 1/hr max).
- Downclocking is ~free on decode: `-lgc 0,2000` costs <2% decode
  (bandwidth-bound) for ~25% less power — the lever for the UPS constraint.
- KERNEL LAW: 6.17.0-1031-nvidia KILLS sustained GPU load (dies on the
  3rd consecutive C8 window, NVRM OOM) and LEAKS ~80 GiB on engine death
  (reboot-only reclaim). Fleet is grub-pinned to 6.17.0-1029 with kernel
  meta-packages apt-mark HELD. Short probes do NOT detect this class —
  regression-test kernel/driver upgrades with >=3 consecutive C8 windows
  and a post-kill memory check.
- Boxes never thermally throttle (<=84 C, <=92 W of 140 W TDP).

## Operational laws (learned the hard way)

- Process matching: use `pgrep -x` / `pkill -x` with the EXACT binary name
  (llama-server, ds4-server) — never -f patterns. -f matches whole command
  lines: it self-matches the ssh command carrying it, matches launch paths
  in the same command, and matches the earlyoom daemon (whose argv lists
  every engine name in its --prefer rule). -x is immune to all three.
  Keep kill and start in separate ssh calls; verify reboots with uptime.
- llama.cpp readiness = /health returns 200 (curl -sf). A TCP answer means
  "still loading". ds4 readiness = /v1/models 200.
- rsync across boxes always with --partial (reboots eat plain partials).
- Transient systemd-run timers die on reboot; use real unit files.
- Alloy on GB10: node exporter MUST use the minimal collector set (a
  default collector hangs on GB10 sysfs and silently kills the scrape).
- GB10 nvidia-smi reports [N/A] for memory.used (UMA): parsers must cope.
- Over-committing the 128 GB pool = UVM page-migration LIVELOCK (hard hang,
  no log, OOM-killer never fires — why earlyoom can't save it). Prevent, do
  not recover: util <=0.92, leave 10-15 GiB free, never co-load big models.
- After ANY reboot: COLD-START the TP=2 stack (stop + rm + fresh launcher;
  GIDs re-resolve). Restart-policy resurrection carries stale RoCE GIDs ->
  ibv_modify_qp crash-loop (109 restarts, 2026-08-24).
- NEVER hot-plug the QSFP DAC into a box with a loaded engine: 2026-08-22
  it wedged spark1 (CX7 bring-up allocates against UMA; power-button reset).
  Drain the engine first, or plug with the box cold. Detection at boot is
  clean and instant with the correct QSFP112 cable.
- NEVER trigger a PCIe rescan (`echo 1 > /sys/bus/pci/rescan`) on GB10:
  2026-08-15 it instantly crash-rebooted BOTH boxes (with a QSFP DAC
  half-detected). CX7 cable detection is hotplug-driven ("Cable insertion"
  in dmesg); if it does not fire, the fix is physical (reseat/other port),
  never a rescan.
- NEVER co-locate docker image builds (or any other memory-hungry work)
  with an engine model load on the same UMA box — 2026-08-10 this wedged
  spark1 to a power-button reset (1.8 GiB avail, network stack starved).
  Stage lanes serially: model READY -> containers built -> next lane.
- Parallel-work default: embarrassingly-parallel jobs (evals, TB lanes)
  run split across both boxes — but one heavy phase per box at a time.
- RESTORE THE DAILY DRIVER before a lane goes idle: 2026-08-17 a paused
  ds4 stayed down ~3 days when an experiment stalled mid-lane. Teardown +
  restore happen in the SAME work session as the experiment, never later.
