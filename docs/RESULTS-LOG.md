# SparkLab Results Log

One entry per benchmark session. Newest first. Raw CSVs live in
`bench/results/`; every claim links its CSV. Pins: [pins.env](../pins.env).

## 2026-08-25 — Peak C1 decode: 89.1 tok/s (Mia methodology), acceptance-driven

User's sparkDash showed ~80 C1; investigated the community/Mia ruler vs
our conservative median. Mia's headline 82.6 = thinking off, ignore_eos,
128-tok forced decode, per-stream rate AFTER first token, best content.
Matched probe (warmed, thinking off, ignore_eos, decode-only, median-of-5)
sweeping content x length on the official-FP8 TP=2 driver:

| content | 128 | 256 | 512 tok |
|---|---|---|---|
| list (highly draftable) | 88.5 | 87.1 | **89.1** |
| code (realistic) | 69.7 | 66.9 | 73.0 |
| generic prose | 55.8 | 52.3 | 50.4 |

**PEAK C1 = 89.1 tok/s** (beats Mia's published 82 on our box, their
ruler). Entirely DSpark-acceptance-driven: predictable sequences draft
near-perfectly -> near hardware ceiling; realistic code ~73; prose ~52.

REPORTING STANCE: two honest numbers, each labelled.
- Peak decode (community ruler, best content, warmed): 89 tok/s.
- Certified record (our closed-loop median, mixed draftable corpus, 3-rep):
  65.8 tok/s — the defensible, can't-poke-a-hole number.
Realistic agent/code work lives ~70-73 decode. Probe:
scratchpad/peak_c1.py (methodology in header).


## 2026-08-24 (C12 sweep) — TP=2 aggregate record 59.3 @C12 (+27%); cold-start-after-reboot law

Completed the TP=2 concurrency curve past C8 (settled Mia config, kernel
1029, adversarial, 3 repeats): C8 47.6 (46.76/47.6/47.87) confirms the
record; **C12 59.33 (59.26/59.33/59.47) — NEW TP=2 aggregate record,
+27% over the C8 ceiling**, zero errors. The seqs-12 scheduler was
underfed at C8; C12 is the config's true ceiling (C16 not run: seats cap
at 12 and 16 is the documented deadlock trigger upstream). Replicas
still hold the overall crown (136.5).

ALSO (the incident that preceded the sweep): after the kernel-pin
reboots, docker's restart policy resurrected both TP=2 ranks with STALE
RoCE GID indexes -> ibv_modify_qp failures -> 109-restart crash-loop.
LAW: after ANY reboot, the TP=2 stack requires a COLD START (stop +
rm containers + fresh launcher run, which re-resolves GIDs); never trust
restart-policy resurrection across reboots. The mini's auto-recovery
already performs a full cold start — verified correct as deployed.
CSV: 20260824-152455-tp2-mia-csweep-adversarial.csv.


## 2026-08-24 (final) — Skepticism round: bisect confirmed, timing explained, v0.6.3 verdict in

Challenged our own kernel conviction three ways:
1. **Module-flavor confound: ELIMINATED.** Both kernels load the same
   NVIDIA OPEN module at 580.173.02; only the kernel+module build pair
   differs (the honest unit of blame for the report).
2. **"Why has nobody reported it?": ANSWERED.** 6.17.0-1031 published to
   noble-updates on 2026-08-20 — four days before our upgrade. The
   ecosystem pins container images, not host kernels; almost nobody runs
   1031 yet. We are early, not wrong.
3. Slow-reclaim alternative: pending a 15-min-wait check on the next 1031
   boot (does not change the sustained-load death, which alone justifies
   the pin).

**v0.6.3 verdict (stable kernel):** boots, but at C8 the memgov build
GATES THE DRAFTER OFF (log: drafts=0, accept=0.0%, concgate=1907
bank-steps) and streams collapse to ~6 tok/s -> bench times out (0
successful windows). Memory reclaims cleanly (1029). Entrpi report
updated: v0.5.6 remains the only fast CUDA config; regression worsened,
not fixed, in v0.6.x.
CSVs: 20260824-*-ds4-v0.5.6-k1029, -v0.6.3-k1029.


## 2026-08-24 (kernel bisect) — MAJOR: kernel 6.17.0-1031 kills sustained GPU load + leaks GPU memory; fleet pinned to 1029

While reverifying the ds4 report, the reproducer exposed something much
bigger. Three independent lanes on kernel 1031: ds4 v0.5.6 runs ~2 clean
C8 windows then DIES (100 request errors, NVRM NV_ERR_NO_MEMORY in dmesg)
— and each death leaves ~80 GiB PINNED with no user process (only a
reboot reclaims it). The definitive one-variable bisect:

| kernel | C8 x3 | post-kill memory |
|---|---|---|
| 6.17.0-1031 (fresh boot) | 56.7, 55.7, DIED (100 err) | 34 GiB (≈81 leaked) |
| 6.17.0-1029 (same box, same everything) | **55.9, 56.0, 56.6 — survived** | **115 GiB — zero leak** |

Retroactive explanations: the TP=2 daily driver's post-refresh headroom
drift (7-12 -> 4-5 GiB) was THIS leak, not page cache; the contaminated
A/B lanes and the TP=2 boot wedge after them were leak-starved memory.

HONEST AMENDMENT to the 2026-08-23 firmware-refresh entry: "no
regression (C1 probe 65.96)" was TRUE for short benches and WRONG as a
general claim — the 1031 regression only manifests under sustained load
(3rd+ consecutive C8 window). Short probes cannot detect it; the 65.8 C1
record itself remains valid (measured in the safe regime, reconfirmed on
1029-era behavior).

ACTIONS: both boxes grub-pinned to 6.17.0-1029 + kernel meta-packages
apt-mark HELD; reproducer script preserved; NVIDIA-facing report drafted
(docs/upstream/). CSVs: 20260824-*-ds4-v0.5.6-cleanAB/freshboot/k1029-*.


## 2026-08-24 (audit) — Full published-results audit: CLEAN; C1 record moves to 65.8

Audited every published claim (one-Spark and two-Spark) against evidence:

1. CSV evidence: all 18 referenced result files exist (4 flagged
   "missing" were prose abbreviations). One real gap FIXED: the
   post-refresh 65.96 probe CSV had never been fetched from spark1
   (now committed: 20260822-210951).
2. Cross-doc consistency: all 10 headline numbers identical across
   results-log, CLAUDE.md laws, and dashboard.
3. Three-repeat rule verified from raw CSV rows for every record:
   TP=2 63.4, Mia settled, K2 54.1 (53.7/54.1/54.9), llama 69.1
   (68.7/69.06/69.4 + spark2 parity twin), ds4 59.89 (59.08/59.89/59.95
   in 20260808-180530).
4. Replica control 136.5 verified as documented synchronized sum
   (68.26+68.27, scaling math in the 08-12 entry).
5. The one out-of-place number — post-refresh 65.96 at ONE repeat —
   REVERIFIED at record grade: 3 repeats [65.04, 65.78, 66.74].

**NEW OFFICIAL C1 DECODE RECORD: 65.8 tok/s draftable** (median-of-3,
TP=2 Mia stack on kernel 1031 + toolkit 1.20.0; was 63.4 pre-refresh —
the firmware refresh gain is real, +3.7%). C8 draftable 36.1 consistent
with settled 35.0. CSV: 20260824-083400-tp2-mia-reverify-draftable.csv.

Verdict: the published record is internally consistent, evidenced, and
methodologically sound. No other reruns warranted.


## 2026-08-24 (later) — Tool chase RESOLVED + anomaly reruns + community dispositions

**1. Tool chase SOLVED — daily driver quality-certified at the ceiling.**
Root cause of the 11% tool score: the eval's "tool" scenarios demand exact
JSON-object arrays in content; with the speed profile (thinking=off) the
model emits sloppy flat arrays. Mechanism confirmed 3/3 both ways
(thinking on -> perfect format). Eval rerun with per-request
chat_template_kwargs thinking=true (harness gained --extra-body):

| category | thinkoff | thinking |
|---|---|---|
| tool | 11% | **78%** |
| json | 66% | 67% |
| exact/needle | 100% | 100% |
| **OVERALL** | 73% | **88%** |

**88% ties the all-time best arm (abliterated) and beats the API (86).**
LAW: on the TP=2 driver, structured/agent tasks should send
chat_template_kwargs thinking=true per request; speed profile stays the
server default. CSV: 20260824-033031.

**2. Mia's "82 tok/s C1" does not reproduce — measured, not mysterious.**
Their own benchmark-0731.py on our cluster: C1 output 64.0 tok/s
(prefill 1549, TTFT 345 ms) — right on our harness's 63-66. Our config
leaves nothing on the table; the published 82 is their-box/their-
conditions. Honest cross-check closed. JSON: 20260824-mia-bench-c1.json.

**3. C8 long-output rerun REFINES the workload-shaped thesis:** 2048-token
outputs gave 36.8 aggregate (vs 46.7 at 512) — longer outputs do NOT
close the gap to community 122+. The remaining difference is largely
MEASUREMENT-shaped: community numbers are server-side decode-window
rates (pure decode, ignore_eos); ours are closed-loop fixed-window
aggregates including TTFT/prefill. Not directly comparable; both stacks
identical under ours. Law updated accordingly.

**4. Community dispositions:** k=3 spec incompatible with 0731 GA (block
size 5 minimum) — closed. SpinCondition thermal patch: diagnostic-only
upstream, watch. tool-eval community: calibrated-v0 2bpw EXL3 scores 94
quality (vs 0xSero build 86) — noted for a future K2-lane upgrade.


## 2026-08-24 — TP=2 CERTIFICATION COMPLETE (quality + 1M + 24h soak)

The MiaAI/Anemll daily driver is now certified on all three axes:

**1. Quality gate (14 scenarios x3):** exact 100%, needle 100%, json 66%,
tool 11%, overall 73%. The tool number is a serving-layer artifact, NOT
model quality (unquantized cannot be below 2-bit quants): a manual probe
confirms basic tool-calling works PERFECTLY (clean tool_calls, correct
args, finish_reason=tool_calls); the eval's hard multi-step scenarios
underperform — template-kwargs interaction suspected, OPEN item.
Prose/retrieval/structured certified at ceiling.

**2. 1M needle ladder — FIRST full-1M retrieval on this stack** (MiaAI's
own README admits none published): needle found at 92K/370K/706K/
**1,010,530 tokens** (96.3% of window), prefill 2.4-2.6K tok/s at depth,
FOUR TIMES faster than the K2 single-box ladder (1M cold: 6.8 min vs
22.5). >window request correctly 400-rejected.

**3. 24h soak: PASSED.** 111 cycles over ~24h, ZERO serving-phase
failures (5 logged failures = the mid-soak firmware-reboot window,
independently verified, frozen thereafter). Survived: a full kernel/
toolkit upgrade + reboots of both boxes mid-soak, multi-hour operator
disconnection, auto-recovery armed (never needed post-reboot). Peak
temp normal, no KV preemption, no wedge.

VERDICT: TP=2 MiaAI/Anemll stack is CERTIFIED as the standing daily
driver — fastest C1 (63-66), community-leading prefill (2.6K), full 1M
verified, 24h stable, self-healing ops. Open items: eval tool-scenario
kwargs; upstream sm_121a rebase watch.
Files: 20260822-211712-tp2-mia-quality-quality.csv, tp2-mia-1m CSVs,
soak-20260822-211803-tp2-mia-soak.log.


## 2026-08-23 (later) — Firmware/driver refresh: both boxes, clean, no regression

Autonomous maintenance (user ruling: normal reboots, no AC cycle needed).
Finding first: platform firmware (UEFI/EC/CX7) was ALREADY latest per
fwupd; driver 580.173.02 already newer than the official 580.159.03. The
actual payload: kernel 6.17.0-1029 -> 1031 (+ matching NVIDIA modules),
container toolkit 1.19.1 -> 1.20.0 (matches the best-tuned community
deployment), linux-firmware, dgx-dashboard.

Procedure: TP=2 stopped clean -> spark2 upgrade+reboot+verify -> spark1
same -> PARITY-OK (kernel/driver/toolkit byte-identical) -> fabric intact
through both reboots -> TP=2 relaunch (no wedge) -> C1 regression probe:
**65.96 decode** vs 63.4 record — no regression, possibly a hair better.
Daily driver back on the freshest stack.


## 2026-08-23 — "Try everything" sweep on the TP=2 daily driver: verdicts

All remaining improvement candidates measured or evidence-closed:

| Experiment | Verdict |
|---|---|
| Prefill baseline (cold->warm, 9K/32K/92K) | **WARM STEADY-STATE ~2,600 tok/s @32K** (2608.7 control run) — ABOVE all community references (1.6-2.2K). Cold first-touch 885-1735 (shape-compile warmup). |
| GPU clock lock (prefill) | **FALSIFIED by control**: locked "gain" (+63%) reproduced exactly at default clocks — pure warmup artifact. Clock-lock no-op law now covers decode AND prefill. GB10 self-caps ~2411-2450 regardless. |
| hazyumps indexer patches | N/A on Anemll stack — sm12x_deep_gemm_fallbacks.py does not exist in the image (native FlashInfer SM121 kernels). Evidence-closed. |
| Newer Anemll image | none published beyond 0.1.1. Watch. |
| Keys mask (VLLM_DSPARK_GPU_REJECTED_CONTEXT_MASK=1) | NEUTRAL (C1 63.4 identical, C8 46.2 ~=46.7). KEPT (correctness under concurrency, zero cost). |
| vLLM upstream sm_121a wheels (PR #52708) | ~6% native-codegen gain coming when stacks rebase. WATCH item. |
| Firmware/driver refresh (DGX OS 7.5.0, July OOM improvements) | queued for a user-present maintenance window (AC-cycle law applies after). |

INCIDENT (honest log): the daily driver's --host 0.0.0.0 relaunch wedged
at boot (~3.5 h down; shm_broadcast spin inside a "running" container —
container-up is a FALSE PROXY, again). Watchdog logged it correctly the
whole time. Recovery: recycle both ranks; came back clean WITH the same
host override -> override exonerated, boot-race class. My monitoring
chain also stalled on a pgrep -f SELF-MATCH (our own ops law violated —
respect it in watcher scripts too).

OPS UPGRADE: mini watchdog now AUTO-RECOVERS the TP=2 cluster (3
consecutive down-ticks -> one rank recycle, max once/hour, Grafana-
annotated). Deployed + live.

Bottom line: no new speed found beyond the existing records — the stack
is at community-leading state (C1 63.4, prefill ~2.6K, 1M ctx, 68%
acceptance). Remaining upside is upstream (sm_121a wheels) and firmware.
CSVs: 20260822-2*/20260823-* tp2-mia-prefill-*, mia-keysmask-*.


## 2026-08-22 (later still) — MiaAI/Anemll lane head-to-head: ADOPTED as the TP=2 standing stack

Research refresh: MiaAI's flagship 2x recipe (872 stars, Anemll image,
nvfp4_ds_mla, results 08-14) + their NEW One-DGX-Spark repo (08-20:
stock432 NVFP4 fixed — future K2-lane relevance). Ran their 2x recipe
@489af95 head-to-head vs our eugr-settled config, same harness.

Config saga: DSPARK_VLLM_IMAGE must be set explicitly (pinned Anemll
digest); DEFAULT_THINKING=max default (same bench trap as eugr — set
off); revision pin overridden to our cached 7872f01b; API binds
localhost -> bench ON-BOX; served name deepseek-v4-flash-dspark.

3-repeat medians (mia-settled: 1M ctx, seqs12, batched8192, thinkoff):

| Point | eugr-settled | mia-settled | Verdict |
|---|---|---|---|
| C1 draftable decode | 63.4 | 63.2 | TIE |
| C1 adversarial decode | 33.4 | 33.4 | TIE |
| C8 draftable agg | 33.3 | 35.0 | tie |
| C8 adversarial agg | 45.7 | 46.7 | tie |
| Draft acceptance | ~30% | **68%** | Mia |
| Context window | 904K | **1,048,576 (full 1M)** | Mia |
| KV pool | — | ~2.49M tokens (nvfp4_ds_mla) | Mia |

Also probed: Mia defaults (seqs6: C8 39.5 — their default throttles C8);
high-agg profile (200K/seqs16/16K-batch: C8 46.9 — no better than seqs12);
long-output C1 (2048 tok): 64.6 — community "82" not reproduced on our
prompts (their number is from short-prompt warm 2048-completion decode).

**LAW LEARNED: our C8 ~46-47 on TP=2 is workload-shaped, not stack-shaped**
— both stacks saturate identically on agent-shaped 512-token turns; the
community's 122-171 aggregates come from long fixed-output pure-decode
workloads where drafts amortize.

**DECISION: MiaAI/Anemll recipe is the standing TP=2 lane** (equal speed,
2.3x draft acceptance, full 1M, ~2.49M-token KV pool, better ops scripts).
eugr b12x kept as alternate. TP=2 C1 record stands at 63.4 (stacks within
noise). Teardown done; daily drivers restored. Warm relaunch:
cd ~/tools/mia-dspark-2x && ./start-deepseek-v4-flash-dspark.sh (spark1).
CSVs: 20260822-12*/13* mia-*.


## 2026-08-22 (later) — TP=2 SPEED CAMPAIGN: AC-cycle law + NEW C1 RECORD 63.4

Research refresh found an Aug-13/18 forum pair on IDENTICAL hardware/versions
reporting (a) hard power-cycle after cabling = +24-43% and 21.4 GB/s NCCL,
(b) a settled 2-node config, (c) UCX per-request RDMA-cache leak fix.
Ran the full matrix. Verdicts:

| Lever | Result |
|---|---|
| **AC power cycle (both boxes, cable in)** | **THE LAW: NCCL 3.03 -> 23.87 GB/s (7.9x, above community 21.4); C1 decode 31.6 -> 64.5 (+104%); the entire "NCCL gap" was stale PCIe/NIC state** |
| draft_sample_method greedy | REFUTED here: 60.9 C1, acceptance 30.7 -> 27.9%. Community greedy gains don't transfer to eugr b12x |
| kv nvfp4_ds_mla | IMPOSSIBLE on this build: "fp8_ds_mla layout only supports fp8 kv-cache" (AssertionError) — Anemll-lineage feature |
| --enable-expert-parallel | FATAL: worker dies ~2 min into load (killed during EP redistribution) |
| seqs12 + lpt1024 + --async-scheduling | neutral within noise; KEPT (concurrency fairness) |
| UCX_MEM_MMAP_HOOK_MODE=none + UCX_RCACHE_MAX_UNRELEASED=1024 | ADOPTED in every TP=2 launch (GanyX19 leak fix: ~14 MB/request UMA drain -> host wedge) |

**Settled-config RECORDS (3 repeats, zero errors):**

| Point | agg | decode | TTFT p50 |
|---|---|---|---|
| draftable C1 | 13.1 | **63.4 — NEW ALL-TIME C1 DECODE RECORD** | 360 ms |
| adversarial C1 | 15.0 | 33.4 | 291 ms |
| draftable C8 | 33.3 | 19.3 | 752 ms |
| adversarial C8 | 45.7 | 12.4 | 631 ms |

C1 crown: TP=2 63.4 > K2 54.1 (+17%) > SparkInfer 38.2 > ds4 30.8.
C8/batch: single-box ds4 (55-58) and replicas (136.5) STILL win — TP=2
remains latency/quality arm, but now the FASTEST single stream we have,
with official FP8 weights and 904K ctx. CSVs: 20260822-*tp2-settled*,
probes 20260822-*tp2-postcycle/tuned-greedy/ep*.
Engines restored (ds4 spark1, K2 spark2). TP=2 warm relaunch ~5 min.


## 2026-08-22 — PHASE 6 FIRST TOKENS: TP=2 dual-Spark serves; performance verdict IN

Historic first: both Sparks serving DeepSeek-V4-Flash-0731 (OFFICIAL FP8,
no quant) as ONE engine over the DAC. eugr recipe @42b3a79, pinned b12x
image (NCCL 2.30.7), TP=2, DSpark k5, max_model_len auto -> 904,448.
Zero request errors across all 12 record runs. hybrid-draft-loader mod
verified applied. Deviations: HF_HUB_OFFLINE=1 (local cache),
thinking=false speed profile (matches all comparator measurements; the
recipe ships thinking=true+effort=high which burned the entire bench
token budget on reasoning — first run produced garbage numbers, discarded
with cause; CSV 20260822-053653 kept as the cautionary artifact).

3-repeat medians (speed profile):

| Point | agg | decode/stream | TTFT p50 |
|---|---|---|---|
| adversarial C1 | 14.7 | 32.9 | 299 ms |
| adversarial C8 | 43.3 | 11.8 | 662 ms |
| draftable C1 | 3.8* | 31.6 | 624 ms |
| draftable C8 | 27.6 | 17.5 | 1577 ms |

*draftable C1/C8 aggregates depressed by tool-call short-completions via
the auto-tool-choice parser (requests complete in few tokens; per-request
overhead dominates) — decode rate is the honest cross-engine metric here.

VERDICT vs our records:
- C1 decode 32-33 LOSES to single-box K2 54.1 (-40%) and roughly ties
  llama.cpp sidecar. The per-layer network hop costs more than TP buys
  on this model at C1 — and our known-open NCCL 3.03 GB/s gap likely
  taxes it further (community TP=2 on this recipe reports 40-67 C1).
- C8 aggregate 43.3 LOSES to a SINGLE box (ds4 58.6) and is 3.2x below
  the two-replica control 136.5. TP=2 is not a throughput play here.
- DSpark acceptance looks ineffective (draftable ~= adversarial decode)
  — Patch-4-class draft issue on this recipe/build is the suspect; NOT
  yet isolated.

ROLE that survives: the TP=2 lane is the QUALITY/CAPABILITY arm — the
only way to serve the official unquantized FP8 checkpoint, with ~900K
native ctx. For speed, replicas + single-box engines keep every crown.
Tuning backlog if we revisit: NCCL gap (3.03), draft acceptance check,
operator max_num_batched_tokens=4096 + retention tweaks, jasl
max-num-seqs sweep. Teardown done; ds4 + K2 RESTORED as daily drivers.
Warm relaunch of TP=2 is now ~5 min (AOT + page cache persist).
CSVs: 20260822-055942 draftable, -062222 adversarial (+053653 thinking
artifact).


## 2026-08-22 — DAC DAY: link VERIFIED end-to-end; NCCL bandwidth gap OPEN

Correct QSFP112 cable arrived and detected INSTANTLY on hot-plug (spark2).
Casualty first: the hot-plug on spark1 (engine loaded, ~5-7 GiB avail)
WEDGED the box — ds4 died, sshd closed all connections, power-button reset
needed. NEW LAW: never hot-plug the QSFP cable into a box with a loaded
engine (CX7 bring-up allocates against the UMA pool). Cold boot with cable
seated detects cleanly.

Validation ladder (all persistent: netplan 40-cx7.yaml, ufw allows):

| Layer | Result |
|---|---|
| Physical | 200 Gb/s both ends, same-port (f1/outer), MTU 9000 jumbo-verified |
| Fabric IP | <lan-ip>/11 (f1np1) + <lan-ip>/11 (enP2 twin) |
| Raw RDMA (1 twin) | 111.85 Gb/s — AT the per-twin PCIe Gen5 x4 ceiling |
| PCIe training | all 4 CX7 functions x4/32GT both boxes (no degradation) |
| NCCL transport | correct: Using network IB, channels across BOTH twins |
| **NCCL bandwidth** | **3.03 GB/s bus — OPEN GAP (expected 10-24)** |

The 3.03 wall held IDENTICAL across: apt NCCL 2.31.2 AND source-built
sm_121 NCCL; GID index forced/auto; CPU-affinity + relaxed-ordering flags;
GDR_LEVEL=SYS; QPS_PER_CONNECTION=4; all_gather AND all_reduce; 1M-16G
sizes (flat from 8M up). Ruled out: memlock (unlimited), PCIe width,
MTU, ufw, wrong-port cabling, single-twin config. GDR 0 as expected
(no peermem; community's GDR-0 hosts still hit 10.2). Remaining suspects:
driver 580.173 host-copy path, mlx5 IRQ placement on GB10 clusters,
or something the vLLM containers set that bare nccl-tests do not.

DECISION: the definitive metric is END-TO-END TP=2 tok/s, not nccl-tests
— decode all-reduces are small and latency-bound. Next lane: bring up the
staged TP=2 recipe (eugr or hazyumps) and measure tokens; treat 3.03 as
an open tuning item unless serving numbers underperform the replica
control (136.5 agg). Both engines RESTORED after validation.
Infra installed: openmpi, libnccl2, ~/nccl (sm_121 build), ~/nccl-tests
on both boxes.


## 2026-08-21 (later) — Bisect CONVICTION: ds4 C8 regression originates in the Metal DSpark PR merge

Four probes (C8 draftable x1 each, :8010, vmm12288 in all):

| Commit | C8 agg | Reading |
|---|---|---|
| v0.5.6 (pin) | 55.1 | baseline |
| 3375a6d Merge PR #2 (Metal DSpark drafter) | **39.1** | **ORIGIN: -29%** |
| f9253ba +CUDA signature mirror amendment | 39.4 | innocent (no change) |
| 3b792c9 +seat-shed hold (v0.5.6.1) | 45.5 | PARTIAL MITIGATION (+6) |
| v0.5.6.2 / v0.5.6.3 | 45.3 | steady |

Story: the Metal drafter PR (#2, robotnursenyc) regresses CUDA C8 batch
throughput by 29% through shared-path changes; the seat-shed hold added
right after masks a third of it; nothing later recovers the rest. The
capacity re-tether (v0.5.6.3) is fully innocent of the C8 loss.

Upstream report draft (for forum 378855 / a new ds4 issue):
  "PR #2 (Metal DSpark drafter, merge 3375a6d) regresses CUDA GB10 C8
  batch aggregate 55.1 -> 39.1 tok/s (-29%), measured usage-token,
  180 s fixed windows, IQ2XXS+DSpark ship config. The seat-shed commit
  871ae69 partially masks it (45.5). C1 is unaffected (+3%). Bisect
  table + CSVs available. v0.5.6 + DS4_BATCH_VMM_BUDGET_MB remains the
  fast configuration on GB10."

State: v0.5.6 daily driver RESTORED (budget 12 GiB). pins unchanged.
~/code/ds4-next left at v0.5.6.3. Upgrade watch: adopt the release that
lands upstream's capacity-tether WITHOUT the Metal-PR regression.
CSVs: 20260821-084432 (.2), -085507 (.1), -090607 (f9253ba),
-091556 (3375a6d).


## 2026-08-21 — ds4 v0.5.6.3 upgrade: REJECTED (C8 regression -18%)

Ran the T26 engine-upgrade runbook on the v0.5.6.3 candidate (commit
b9c97ad, built in ~/code/ds4-next, served :8010 via wrapper).

Acceptance vs v0.5.6 logged medians (max regression allowed 5%):

| Point | v0.5.6 | v0.5.6.3 | Delta |
|---|---|---|---|
| C1 draftable | 27.1 | 27.9 | +3% PASS |
| C1 adversarial | 22.2 | 21.9 | -1.4% PASS |
| C8 draftable | 55.1 | **45.3** | **-17.8% FAIL** |
| C8 adversarial | 58.6 | **47.0** | **-19.8% FAIL** |

Isolation attempts (all produced the IDENTICAL ~45.3 C8, spread <0.6):
1. Auto capacity-tether pool too small (1.31 GiB)? -> relaunched with
   DS4_BATCH_VMM_BUDGET_MB=12288 (line shows budget=12.00): NO CHANGE.
2. New seat-shed hold (DS4_CONT_HOLD_SHED_S default 5s, v0.5.6.1)? ->
   relaunched with =0: NO CHANGE.
The cap is behavioral and intrinsic to something else in the 13 commits
(remaining suspects: decode-phase stream heartbeat, DSML no-tools cut,
the re-tether logic itself even when overridden). Not bisected — 30 min
per config; queued as an optional lane.

Notes for the record: the capacity-tether DOES work as designed (candidate
booted with budget=1.31 GiB [plan 2.19, capacity 1.31] with no env), so
v0.5.6.3 fixes the degradation mechanism natively — it just costs 18% of
batch throughput on our box. C1 is unaffected (+3%).

VERDICT: stay on v0.5.6 + DS4_BATCH_VMM_BUDGET_MB=12288 (restored,
serving). pins.env UNCHANGED. Candidate tree kept at ~/code/ds4-next for
a future bisect; rollback binary ds4-server.v0.5.6 saved. Worth reporting
upstream (forum 378855) with the C8 numbers.
CSVs: 20260821-071940/-072904 accept, -073845 record, -075842 budget,
-081806 nohold.


## 2026-08-20 — B3: llama.cpp bump verdict — NO pin change

Built llama.cpp master f9779dda8 (separate tree ~/tools/llama.cpp-new;
pinned 687e778 build untouched). Findings:

1. Sidecar C1 draftable (n3, 1 slot, 3 repeats): decode median 31.05
   (31.08/30.73/31.05) vs 32.3 on our pinned build — ~4% SLOWER. No speed
   reason to bump.
2. #26741 (parallel+spec garble): STILL OPEN upstream. The
   never-parallel-with-spec law stays regardless of build.
3. Abliterated dflash companion: still does NOT serve — llama-server died
   at 9.5 min into draft-model load on f9779dda8 (card validated only via
   llama-cli at fffbcbdb). Companion remains cli-only; target-only serving
   stands (16.3 decode, quality 88%).

VERDICT: keep pin 687e778. Re-check on next upstream DSpark churn or when
#26741 closes. New tree left in place for future tests.

OPERATIONAL NOTE (honest log): B3 stalled mid-lane 08-17 -> 08-20; spark1
served NOTHING for ~3 days (ds4 was paused for the lane and not restored;
watchdog logged it). Rule reinforced: RESTORE THE DAILY DRIVER before any
lane goes idle — teardown-and-restore belongs in the same work session as
the experiment, never deferred.
CSV: 20260820-104128-llamacpp-f9779dda8-sidecar-draftable.csv.


## 2026-08-17 — Pre-DAC B experiments: warm-prefix law + K2 tune (NEW C1 record 54.1)

**B2 — warm-prefix at depth (K2, 1M window, live server):**

| Depth | Cold | Warm (same prefix, new question) | Cached tokens |
|---|---|---|---|
| 92K | 75.2 s | 22.6 s | 64,768 (partial) |
| 370K | ~5.5 min (ladder) | **8.8 s** | 258,048 |

(370K cold leg's HTTP response was lost to a LAN stall; server-side prefill
completed — which is what armed the warm hit. Cold reference from the
08-14 ladder.) **Law: warm-prefix turns deep-context turns from minutes
into seconds (~37x at 370K).** 1M sessions are usable if the session
prefix stays cached. The 92K partial hit (64K/92K) shows retention limits
— retention4096 was added in the same tune below.

**B1 — K2 concurrency rescue (one restart, all knobs together:**
MAX_NUM_SEQS=12, CUDAGRAPH_CAPTURE_SIZES=1,2,4,6,8,12 (ship config only
captured to 6 — C8 ran EAGER, the smoking gun), MAX_CUDAGRAPH_CAPTURE_SIZE
=12, --long-prefill-token-threshold 1024,
VLLM_PREFIX_CACHE_RETENTION_INTERVAL=4096 via compose.override.yaml):

| Metric | Ship config | Tuned | Delta |
|---|---|---|---|
| C8 draftable aggregate | 14.3 | **21.5** | +50% |
| C8 TTFT p50 | 8,617 ms | **1,483 ms** | 5.8x better |
| C1 decode (draftable) | 50.2 | **54.1** | +8% — NEW box C1 record |
| C1 TTFT p50 | — | 939 ms | — |

3 repeats each, zero errors. C1 54.1 (54.11/54.92/53.72) beats the 50.2
record — likely the added capture sizes covering the k5 verifier shapes.
C8 aggregate still below ds4 (~55): K2 remains the single-stream/long-ctx
tool, but concurrency is now tolerable instead of broken. Tuned .env is
the new K2 standard config (in place on spark2).

**B4 — ds4 upstream:** v0.5.6.3 exists (13 commits past our pin). Contains
the OFFICIAL degradation fix ("Batch cache budget re-tethered to capacity",
citing our forum thread 378855/86), decode-phase stream heartbeats, DSML
no-tools cut, Metal DSpark work. RECOMMEND: parity upgrade lane
v0.5.6 -> v0.5.6.3 on both boxes after B3; pins.env bump + re-baseline.
CSVs: 20260817-001820 warmprefix; 20260817-082731 + -083917 k2-tuned.


## 2026-08-15 — Abliterated model: validated once, kept on-disk, NOT in rotation

Policy (user ruling): keep an uncensored/abliterated DeepSeek available for
possible future use cases; validate once; do NOT use generally. ds4 + K2
stay the serving engines.

Artifact chosen: apetersson/DeepSeek-V4-Flash-0731-Abliterated-DS4-Quality128
(GGUF, ungated, ONE-box). Rejected the drowzeys/joeynyc FP8 variants — those
are 2-node TP=2 only (gated + won't load until DAC). Stored ~/gguf/abliterated
on spark1. SHA-256 all 3 files MATCH the model card:
target 2cfc36b7..., ds4-companion cd8593a2..., llamacpp-companion 0582de4d.
Quant: Quality128 policy — sensitive routed experts (L10,14,30,34,37-42)
kept in EXACT native MXFP4; rest IQ2_XXS/Q2_K; Q8 attention. Abliteration
touched only 36 attn.wo_b tensors (minimal capability impact by design).

Test method: ds4 paused (power/UVM), served target-only on llama.cpp @687e778
(:8001, ctx16384, 1 slot), 21 GiB headroom. 3-repeat medians, our harness.

| Metric | draftable | adversarial |
|---|---|---|
| C1 decode tok/s | 16.3 | 16.3 |
| C1 aggregate | 7.4 | 7.5 |

**Quality eval (14 scenarios x3): OVERALL 88%** — json 78 / tool 67 /
exact 100 / needle 4K+16K 100. HIGHEST of any arm we have run: API 86,
ds4-Q2 83, llama UD-IQ2_M 81, K2 79. Expected: Quality128 preserves the
sensitive experts natively, so it should beat aggressive 2-bit quants; and
abliteration barely touches capability. Zero request errors, coherent output.

Speed caveat: 16.3 is TARGET-ONLY (no speculation) — comparable to
llama.cpp UD-IQ2_M target-only 19.7, a bit lower as Quality128 is heavier
(95.8 GiB). The DSpark companion (llamacpp-DSpark-support.gguf) would roughly
double it BUT our pinned llama.cpp @687e778 cannot load it: "dflash requires
ctx_other to be set" — the companion uses the newer dflash schema needing
upstream commit fffbcbdb (2026-08-02); our build predates it. Noted, not
chased (one-time validation). If we ever adopt this model, bump llama.cpp.

Teardown: llama-server stopped, ds4 daily driver restored (VMM budget set).
CSVs: 20260815-140805-ablit-q128-target-draftable.csv,
20260815-142120-...-adversarial.csv, 20260815-143404-ablit-q128-quality.csv.


## 2026-08-15 — Repo re-checks: tonyd2wild (MAJOR: Patch 5) + joeynyc

**tonyd2wild/DeepSeek-v4-Flash-0731-DSpark-1M-NVFP4-KV-2x-DGX-Spark** (380
stars; the most battle-tested 2-node recipe). New since our last look:

1. **Patch 5 — stop-string decapitation (IMPORTANT for agent serving, any
   vLLM stack incl. K2):** vLLM v1 matches client `stop` strings against
   the WHOLE stream including the reasoning segment. Think-in-prompt models
   restate phrases like "Question:" mid-reasoning -> stop fires inside
   reasoning -> reasoning-end never arrives -> parser returns content:null.
   Looks like a model failure; is a serving-layer one. Their fix: stops
   dormant until reasoning-end token appears (GSM8K n=50: 8-15 nulls ->
   1 null, 0.66-0.84 -> 0.98). OUR exposure: bench harnesses send NO stop
   strings (verified) — our numbers are clean. But agent clients (Hermes
   etc.) that send stops WILL decapitate answers on K2/vLLM. Caveat logged;
   patch candidate if we see content:null from agents.
2. Patch 4 (known): draft loader drops 12 shared-expert tensors on 0731 ->
   acceptance collapse, ~half speed, quality unchanged. Their numbers with
   it: 78 tok/s peak / ~55 typical on TP=2.
3. Ops trap: bind-mounted patch files are NOT synced to the worker by
   their launcher — must exist at the same path on BOTH nodes or you run
   half-patched. Add to Phase 6 checklist.
4. Issue #18 mechanism B: rare reasoning runaway (end-marker never emitted)
   — runs to max_tokens; unrelated to stops; no fix yet.

**joeynyc/deepseek-dspark-optimized** (re-check; created 08-12): still
abliterated-model-only (not for us). Worth borrowing: digest-pinned Anemll
image, worker-rank-starts-first ordering, general-vs-coding profile split
(k and batch knobs per traffic type), validate-before-launch + rollback
scripts, explicit "not 24h-soak-certified" honesty. DSpark k=3 (vs
tonyd2wild k=5) is their pick for the same hardware — a knob to sweep in
Phase 6, not a conclusion.


## 2026-08-14 — DSpark quality A/B: ZERO measured cost; community claims traced to bugs

Community claim: "DSpark drops quality significantly." Investigated + tested.

**A/B on K2 (spark2), identical 14-scenario quality eval, 3 repeats/arm:**

| Arm | json | tool | exact | needle | OVERALL |
|---|---|---|---|---|---|
| DSpark k5 ON | 67% | 33% | 100% | 100% | **79%** |
| DSpark OFF (MODE=off) | 67% | 33% | 100% | 100% | **79%** |

Byte-identical category profile. Speculation with proper verification is
lossless (target verifies every drafted token); our stack confirms it.
(K2 tool-call 33% vs ds4/API ~67% is a K2/parser trait, in BOTH arms —
not a DSpark effect.)

**Where the community claims come from (real bugs, not the method):**
1. llama.cpp #26741 (code-audited): DSv4 GARBLES output when parallel
   (-np>1) AND speculation are on together — rollback-restore replay
   poisons compressed KV. Single-slot+spec clean; parallel spec-off clean.
   **CAVEAT lands on OUR 'llama.cpp 12-slot + DSpark n3' record rows**
   (C8/C12 cells). Spec-off records (69.1 etc.) immune. Our S3 sidecar
   C1 lane (1 slot) also immune.
2. vLLM #40969: PIECEWISE cudagraph + spec leaks visible '#' tokens.
3. Perf-only issues misread as quality: draft loader silently dropping 12
   shared-expert tensors (tonyd2wild patch 4; acceptance collapse, output
   provably unchanged), vLLM #51009 position-1+ acceptance collapse.

Rule adopted: on llama.cpp NEVER combine --parallel >1 with DSpark until
#26741 is fixed upstream (our slot law already pushes spec-off at high C,
so no record changes — but the +DSpark C8/C12 rows get a quality asterisk).
CSVs: 20260814-153359-k2-dspark-on-quality.csv,
20260814-153833-k2-dspark-off-quality.csv. K2 restored to MODE=dspark.


## 2026-08-14 — K2 long-context probe: 1M ON ONE BOX VERIFIED

Needle-retrieval ladder against K2 on spark2, MAX_MODEL_LEN=1000000
(relaunched; loads and serves fine at util 0.85 with monitoring on,
~8 GiB avail). New probe harness: bench/longctx_probe.py (usage-exact
token counts, needle at 40% depth, temp 0).

| Prompt tokens (usage) | Prefill tok/s | Wall | Needle |
|---|---|---|---|
| 22,609 | 1,037 | 22 s | FOUND |
| 92,473 | 1,284 | 72 s | FOUND |
| 184,928 | 1,314 | 141 s | FOUND |
| 369,838 | 1,114 | 5.5 min | FOUND |
| 705,792 | 835 | 14.1 min | FOUND |
| **993,735** | **735** | **22.5 min** | **FOUND** |

**First-class goal partially landed: 1M context runs on ONE Spark** (the
plan assumed it needed two + DAC). 6/6 needle retrievals, zero errors.
Prefill degrades gracefully (1.3K -> 735 tok/s at full depth); a cold
1M prompt costs ~22 min — prefix caching is what makes it usable
interactively. Note: single-needle retrieval proves KV capacity +
addressing, not full semantic quality at depth (community caveat stands).
One >1M attempt correctly 400-rejected (window enforced, no crash).
CSVs: 20260814-191211 + 20260814-193906 -k2-9b2b1e3-longctx.csv.


## 2026-08-13/14 — K2 recipe TRIAL on spark2: NEW C1 decode record 50.2 (draftable)

Ran tpurtell/deepseek-v4-flash-0731-exl3-k2-spark @9b2b1e3 on spark2
(util 0.85, ctx 262144, DSpark k5 on, .env set explicitly to dodge the
empty-string CUTE DSL crash). ds4 on spark1 stopped first (power rule).

**Coexistence problem SOLVED: server loaded, captured graphs, and served
with Alloy collectors AND earlyoom running the whole time.** Steady state
112/121 GiB used, 9 GiB avail (just under our 10-15 comfort band — watch).
Zero request errors across all 12 runs; no throttle; power max 76.7 W.

3-repeat medians (our harness, usage tokens, fixed windows, max_tokens 512):

| Workload | C1 decode | C1 agg | C8 decode/stream | C8 agg | C8 TTFT p50 |
|---|---|---|---|---|---|
| draftable | **50.2** (49.9/50.2/55.6) | 10.4 | 16.3 | 14.3 | 8.6 s |
| adversarial | 25.2 | 11.8 | 8.5 | 15.9 | 4-56 s |

Verdict:
- **NEW box C1 decode record: 50.2 tok/s draftable** (prior 38.2 SparkInfer
  K3; ds4 30.8). Community 52 claim REPRODUCES on long draftable output.
  Workload-shaped as predicted: adversarial C1 falls to 25.2 (drafter wash).
- **NOT a batch/agent server on our harness**: C8 aggregate 14-16 vs ds4
  ~50 and llama.cpp 67.8; C8 TTFT seconds-long (one repeat 55.6 s);
  concurrent-prefill scheduling collapses under 8-way agent-shaped load.
  Their 62.7@C8 comes from uniform long-output workloads, not ours.
- Role: best long-generation single-stream engine we have run. Candidate
  for C1-heavy long-code sessions on spark2; ds4 stays daily driver.
- 1M-ctx-on-one-box claim not yet tested (KV pool present; needs a
  long-context probe run).

CSVs: 20260813-195750-k2-9b2b1e3-draftable.csv,
20260813-202227-k2-9b2b1e3-adversarial.csv. Engine left UP on spark2;
ds4/spark1 restore pending user call.


## 2026-08-13 — Research: route to >38 C1 without the SparkInfer caveats

Question: can spark2 hit the 38.2 C1 record without the two SparkInfer
problems (memory squeeze vs monitoring; 9.3 short-turn aggregate)?

**Answer: a NEW recipe (2026-08-10/11) targets exactly this and claims to
beat 38 outright: tpurtell/deepseek-v4-flash-0731-exl3-k2-spark** (fork of
the 0xSero recipe we benchmarked; 0xSero is top contributor).

What changed vs the recipe we ran:
- Checkpoint EXL3 **K2** ~2 bpw experts, **78.2 GiB** (vs ~105 GB K3) —
  ALL 256 experts kept, no REAP pruning, plain HF safetensors.
- Native 3-block DSpark drafter, k=5, on by default (`MODE=off` to disable).
- util **0.85** (vs our forced 0.93) → real headroom; should coexist with
  earlyoom + collectors. This addresses caveat #2 directly.
- Compact 432-byte NVFP4 sparse-MLA KV (the true record 0xSero disabled);
  measured 1.18M-token KV pool → 1M ctx on ONE box claimed.
- Pins: nvcr vllm:26.02-py3, local-inference-lab/vllm@3003860,
  tpurtell/sparkinfer-glmrt@fefb9c5, model rev dff9afc.

Reported numbers (their harness + one independent forum repro, timhbl):
- C1 code decode (512-tok outputs): **52.47 median** (accept 63.8%).
- Independent repro: C1 **57.3**, C8 62.7, C64 114.5 aggregate
  (MAX_NUM_SEQS=12, util 0.85); same harness put ds4 v0.5.5 at 21.5 C1.
- Honest matched short-turn (2048 fresh prompt / 128 out, no cache):
  C1 24.7, C4 31.7 aggregate, acceptance only 28.9% — the 52 is
  workload-shaped (long draftable code), NOT a universal chat rate.
- llama-benchy C1: 1317 pp / 25.5 tg. Tool Eval Bench 92/100.
- Their 2x-Spark TP2-over-RoCE row: C1 26.5 — barely above one box;
  reinforces our replica-beats-TP2 stance pre-DAC.

Known gotchas (from the repro post): compose passes `${VAR:-}` as EMPTY
strings which crash the CUTE DSL kernel compile (`KeyError: ''`) — set
CUTE_DSL_ARCH=sm_121a, GPU_MEMORY_UTILIZATION, MAX_MODEL_LEN explicitly in
.env. Never repeat entrypoint flags in EXTRA_VLLM_ARGS (last-wins dupes).

Assessment vs our records: on OUR fixed-window matched harness this may
land ~25-31 C1 (their matched row), i.e. below our ds4 30.8 — but the
long-generation decode rate (52-57) is the regime agent code-gen actually
lives in, and the independent C8 62.7 with C64 headroom + 1M-ctx-on-one-box
makes it strategically important beyond C1. Needs OUR harness to settle it.
Not yet run — spark2 trial pending (power rule: stop ds4 on spark1 first,
or downclock both). Sources: NVIDIA forum thread 379863; github
tpurtell/deepseek-v4-flash-0731-exl3-k2-spark.


## 2026-08-12 — DEGRADATION SOLVED (upstream root cause + fix) + community methodology sweep

Researched NVIDIA GB10 forums/blogs for methods we missed. Two land directly:

**(A) ds4 sustained-load degradation — ROOT CAUSE FOUND, our "cause open"
finding is now closed.** Engine author (entrpi) explains it: per-bank
compressed-KV + indexer caches map pages GROW-ONLY; under agentic reuse each
bank walks to its max extent (several GB), squeezing the page cache holding
the weights -> MoE refaults from disk every step -> throughput cliff. This is
EXACTLY our 2x-slowdown finding.
FIX APPLIED to daily driver: `DS4_BATCH_VMM_BUDGET_MB=12288` pins the pool as
a hard cap; over-budget admissions rejected cleanly (watch `cont admit
rejected`) instead of mapped into oblivion. Trim-on-evict ships in ds4 v0.5.1.
Our earlier soak "self-heal with idle gaps" was the pool churning back down;
the pin prevents the growth entirely, even under sustained load.

**(B) UVM page-migration livelock — explains our spark1/spark2 wedges.** Forum
consensus: on GB10 if allocation creeps past the pool you get NOT a clean OOM
but a UVM page-migration livelock that hard-locks the box, no log, OOM-killer
never fires (why earlyoom couldn't save spark1). Real fix = headroom: keep
util <=0.92, leave 10-15 GiB free, never co-load. Validates our swap-off +
memory-gate + one-heavy-phase doctrine (learned the hard way; now confirmed).

**(C) Downclocking is ~free on decode (ACTIONABLE for our UPS problem).**
Multiple GB10 users: -lgc 0,2000 (vs stock ~2800-3000) costs <1-2% DECODE
(bandwidth-bound, clocks irrelevant) but ~25% power (60W vs 80W) and kills
throttle-shutdowns. Candidate: run both boxes at 2000 MHz to fit the 600 VA
UPS with negligible decode loss. (~10-12% loss on PREFILL, which is
compute-bound — acceptable given Spark's prefill headroom.) Test when useful.

**(D) Phase 6 / dual-Spark — Stage-D DSpark fix (vLLM PR#49133):** the 2x
recipes' DSpark draft silently inherits the target's NVFP4 quant config and
runs the WRONG path; forcing draft to native MXFP4 + `moe_backend:b12x` (draft
only; target trunk stays flashinfer_b12x) gave 16.7 -> 45-64 tok/s (2.7-3x) on
a community 2-node run. Add to the DAC-time bake-off checklist.

**(E) Methodology dead-ends confirmed (vbalko weekend deep-dive):** generic
KV tricks (TurboQuant) are irrelevant on V4 (KV already FP8); llama.cpp Flash
Attention auto-disables on V4 (head_dim=512 needs K_seqlen%256==0, never true
on the compressed path) -> 41/43 layers fall back to slow explicit attention;
llama.cpp MTP port had a 56x regression vs ds4. Lesson: V4 is too custom for
off-the-shelf opts; read the model source first. We correctly did NOT chase
these.

**(F) Prefill is the real interactive bottleneck for coding agents on big
repos** (community note): decode tok/s is what we optimized, but OpenCode-style
use on established codebases is prefill-bound. Our ds4 prefill measured poorly
(40-50 cold 2K) vs community 776-1000 at depth — worth a dedicated prefill
sweep (llama-benchy --pp) if coding-agent latency matters. Noted, not chased.


## 2026-08-12 — C1 speed experiments + SparkInfer EXL3 (new decode record)

Chased C1 beyond our 31 aggregate ceiling. Swept ds4 (styles01 env,
mtp-draft, clock lock) and llama.cpp (1-slot, n-max 2/3/4, p-min) — all
landed 27-33; the community "40 tok/s" recipe env did NOT reproduce on our
honest harness. Clock lock was a no-op (GB10 self-caps ~2.4 GHz — bandwidth
bound, not clock bound). Then SparkInfer (0xSero EXL3/Trellis + SparkInfer
kernels), 6 launches to fit (recipe assumes a BARE box; our ~9 GiB
monitoring tax forced GPU_MEM_UTIL 0.9465->0.93, ctx 262K->32K,
VLLM_ENGINE_READY_TIMEOUT, and stopping collectors+earlyoom so the FULL
cudagraph capture spike fit).

**Honest C1 metric = decode tok/s (inter-token rate; what the community's
"38" reports, TTFT excluded):**

| Engine | C1 decode tok/s |
|---|---|
| **SparkInfer EXL3** | **38.2** (NEW record; reproduces community 38) |
| llama.cpp sidecar n3 | 32.3 |
| ds4 ship (DSpark on) | 30.8 |

SparkInfer's Trellis non-uniform quant reads fewer bytes/token — the one
lever that moves a bandwidth-bound box. +18% over our prior best.

**Caveats (why it is NOT our daily driver):**
1. Short-turn AGGREGATE is poor (9.3 tok/s): vLLM per-request overhead
   dominates when completions are short. Its 38 decode only pays off on
   long single-stream generations; ds4's native low-overhead server keeps
   aggregate~=decode and feels faster for interactive turns.
2. Cannot coexist with our monitoring — needed earlyoom off + collectors
   stopped just to fit the cudagraph capture. Not an always-on option on an
   instrumented box.

Config deviations from the pinned recipe (all "fit our box", not speed
tweaks): util 0.93, ctx 32768, engine-ready timeout 3600. Comparison stays
fair (neither materially changes single-stream decode rate).
CSV: 20260812-122219-sparkinfer-exl3-draftable.csv.

## 2026-08-12 — Terminal-Bench: STOPPED (not pursued)

Ran 3 lanes (ds4-Q2, UD-IQ2_M, API ceiling), no-thinking harness. Partial:
API 7/15, UD-IQ2_M 1/11, ds4-Q2 incomplete. Finding kept: the local agentic
ceiling is capped by DECODE SPEED, not quant damage — grid-pattern solved by
both API and 2-bit local; the API's speed edge (not quality) closed most of
the 47%->9% gap via fewer agent_timeouts. Corroborates the structural quality
gate (quant damage ~zero) on real agentic work. DROPPED because: cannot match
published scores at local decode speed (no-thinking forced by ~20 tok/s), AND
results are private, so leaderboard comparison has no value. Throughput matrix
+ quality gate carry the load-bearing conclusions. Boxes freed 2026-08-12.

## 2026-08-10 — TB campaign launched (3 lanes) + spark1 OOM incident

Scope per user ruling: quality is quant-level, so 5 throughput states
collapse to 3 TB lanes: ds4-Q2, UD-IQ2_M, API ceiling. 15 tasks each,
terminus-2 scaffold, no-thinking (local speed economics; documented),
90-min task budgets. Verification burn-down: dataset fetch -> parser
(reasoning-format) -> timeout -> thinking; 4 rounds to a viable config.

INCIDENT: spark1 wedged (OOM thrash, 1.8 GiB avail, network dead) when
Lane C container builds were launched during Lane A's model load —
operator error, staged-lane rule added to CLAUDE.md. Lane B (UD-IQ2_M,
spark2) unaffected and running. Lanes A/C relaunch staged after recovery.

## 2026-08-10 — TWO-BOX REPLICA RECORD: 136.5 tok/s aggregate

Synchronized unattended run (systemd timers, both boxes, localhost-only
measurement paths). CSVs: `20260810-093000-spark{1,2}-llamacpp-adversarial.csv`.

| Box | repeats | median agg | point end-times (UTC) |
|---|---|---|---|
| spark1 | 68.26 / 68.26 / 68.26 | 68.26 | 09:35:58, 09:41:56, 09:47:55 |
| spark2 | 68.27 / 68.27 / 68.40 | 68.27 | 09:35:57, 09:41:57, 09:47:54 |

**Total: 136.53 tok/s** across two independent replicas (llama.cpp record
config each). Boxes finished every repeat within 2 s of each other — true
synchronized measurement. Scaling efficiency vs 2x single-box record:
136.5/138.1 = 98.9% (the ~1% is shared-room thermals / normal variance).

This is the baseline the future TP=2 lane must beat. Per the plan's
prediction: independent replicas are near-perfect for throughput; TP=2's
only winnable ground is single-session capability (1M context).

## 2026-08-10 — 18h SOAK: PASSED (and the degradation inverted)

`soak done: 70 cycles, 0 failures` — 223 measurement points over 18 h of
mixed load (C1/C8/C4, alternating corpora, idle gaps). Zero request errors.
Throughput drifted UP, not down: first cycles C8~32 tok/s (engine inherited
warm from the needle-repro session), final cycles C8 57.3 / C4 46.1 / C1
23.0 — full fresh-server health. ds4 self-recovers under cycled load with
idle gaps; the documented degradation evidently requires sustained
uninterrupted serving. Stability gate for Milestone 4: PASSED.

## 2026-08-10 — QUALITY VERDICT: API reference arm closes the case

`20260810-075320-api-reference-quality.csv` — full-precision DeepSeek API,
same 14 scenarios, same sampling (temp 1.0 / top_p 0.95), 3 repeats.

| Arm | Overall | tool-multi | json-invoice | needles + exact |
|---|---|---|---|---|
| **API (full precision)** | **86%** | 0/3 | 0/3 | 100% |
| ds4 Q2 ship | 83% (79-86 band) | 0/3 | weak | 100% |
| llama.cpp UD-IQ2_M | 81% | 0/3 | 0/3 | 100% |

The API fails the IDENTICAL scenarios as both quants. Conclusion: the
failures are model-level behavior at temp 1.0 (or checker strictness),
NOT quantization damage. **Measured quant quality cost: ~zero** on this
suite. The 2-bit recipes are vindicated for publication; the quality gate
for Milestone 4 is PASSED pending only the Terminal-Bench cross-check.

## 2026-08-10 — spark2 SILICON PARITY: CONFIRMED

Unattended pipeline (Wi-Fi sync 280 GB -> engines -> localhost benches).
CSVs: bench/results/*spark2*.csv (PARITY tag, 3 repeats each).

| Config | spark2 median | spark1 record | delta |
|---|---|---|---|
| llama.cpp 12-slot spec-off, C12 adversarial | **69.07** (±0.54) | 69.06 | +0.0% |
| llama.cpp 12-slot spec-off, C12 draftable | 62.49 (±1.40) | 62.77 | -0.4% |
| ds4 spec-off, C12 adversarial | 58.07 (±1.41) | 59.89 | -3.0% |

The two units are statistically identical on the record config (0.0%!).
The 3% ds4 gap is within the config's run-to-run band. No silicon lottery,
no thermal difference. Both boxes are record-capable.

Two-box replica projection: ~138 tok/s aggregate. Measured result follows
from the scheduled synchronized run.

## 2026-08-09 — COMPLETE RECORD MATRIX (all cells 3-repeat medians)

| State | Workload | C1 | C8 | C12 |
|---|---|---|---|---|
| ds4 ship (DSpark on) | draftable | 27.1 | 55.1 | 54.6 |
| ds4 ship (DSpark on) | adversarial | 22.2 | 58.6 | 57.8 |
| ds4 spec-off | draftable | 20.8 | 55.6 | 56.2 |
| ds4 spec-off | adversarial | 21.1 | 59.0 | 59.9 |
| llama.cpp 12-slot spec-off | draftable | 19.7 | 33.1 | **62.8** |
| llama.cpp 12-slot spec-off | adversarial | 19.7 | 46.0 | **69.1** |
| llama.cpp 8-slot spec-off | draftable | n/a* | **62.2** | n/a* |
| llama.cpp 8-slot spec-off | adversarial | n/a* | **67.8** | n/a* |
| llama.cpp 12-slot +DSpark n3 | draftable | 29.7 | 39.5 | **67.4** |
| llama.cpp 12-slot +DSpark n3 | adversarial | 25.8 | 38.2 | **65.9** |

n/a*: S3 C1-only by design (C8/C12 folded into 12-slot VERIFY rows listed
under S3 below); S4 canonical point is C8 (slot law: C must equal slots —
mismatched cells are the degenerate case S3 documents). S3 C8/C12 verified
medians: draftable 33.1/62.8, adversarial 46.0/**69.1**. S4 C8 adversarial
**67.8**.

**Box record stands: 69.1 tok/s aggregate (llama.cpp, 12 slots, C12,
spec off, adversarial).** Runner-up 67.8 @ C8 with 8 slots — same plateau,
better TTFT. Best C1: llama.cpp +DSpark 29.7 / ds4 ship 27.1.

ds4 fresh prefill sweep (llama-benchy, cold 2K prompts): ~40-50 tok/s —
far below the community ~1000 tok/s claim; llama.cpp measures 437-467 on
the same instrument. The community figure evidently reflects a different
measurement shape (warm prefix banks / native harness). Instrument-shape
caveat recorded; our agent-bench TTFT numbers stand as the practical view.

Degradation event: did NOT recur through the entire instrumented re-run
(same workloads, health probes clean, mem steady 5.6-6.0 GiB). Deliberate
repro (two full quality-eval doses incl. 16K needles, C1 probes between):
NEGATIVE — throughput steady 23-25 tok/s, memory steady. Needle hypothesis
disproven as standalone trigger. Root cause remains open; the 18 h soak
(started 2026-08-09) is the standing trap: per-cycle CSVs + Grafana
timeline will timestamp any recurrence. Quality band note: repeated full
evals scored 79/81/83/86% — temp-1.0 sampling noise; needles+exact 100%
every run.

## 2026-08-09 — RELIABILITY FINDING: ds4 degrades under sustained bench load

After ~3.5 h of continuous serving (quality eval + record runs, hundreds of
unique-prefix sessions), ds4 v0.5.6 ship config degraded ~2x: C12 adversarial
57.3 -> 41.2 -> 40.6 across repeats; one C1 point fell to 5.98 tok/s; the
llama-benchy prefill sweep on the same degraded server showed multi-minute
prefill latencies with huge variance. Host memory at discovery: 112 GiB used,
9.2 GiB available.

**Hypothesis v1 (weakened)**: KV-bank/cache growth + memory pressure.
Against it: one fresh restart (gap-matrix S2) stayed degraded, and RSS/
memory profile looked normal for UMA serving.
**Update 2026-08-09 later**: a planned discriminating reboot never executed
(operator script bug), yet a kill-everything + fresh start DID fully recover
(C1 28.6, C12 54.6). So the state is process-adjacent, not host-permanent,
but one earlier fresh restart did not recover — trigger still ambiguous.
Degraded rows show clocks normal, power HIGH (89 W at C1 for 5.7 tok/s):
the engine burns compute on internal work. Instrumented re-run in flight
with health probes between blocks to catch the trigger in the act.

**Consequences**:
- ds4 S1 ship records from this window are VOID (marked; will re-run fresh).
- ds4 prefill sweep VOID; re-run on fresh server pending.
- This is soak-class evidence: any long-lived ds4 deployment needs bank/cache
  limits tuned (engine has an operator memory floor per its changelog) or
  periodic restarts. Candidate upstream report with logs + Grafana timeline.
- Grafana MemAvailable panel captured the decline — first live catch for the
  monitoring stack.

Clean cells unaffected (fresh servers): all llama.cpp records, ds4 spec-off
C8/C12 adversarial records, quality evals (ran early in each session).

## 2026-08-09 — Phase 2 matrix COMPLETE: slot law + sidecar lane

CSVs: `20260808-205144` (SLOTPROBE), `20260808-210526`/`20260808-211425` (SPECLANE).

**Slot-matching law (verified, 3 repeats):** llama.cpp C8 with `--parallel 8`:
67.82 tok/s (±0.27) vs 33.06 with 12 slots. Rule: **set --parallel equal to
expected concurrency.** Throughput plateaus by C8 when slots match.

**DSpark sidecar (n-max 3, 1 repeat):** C1 draftable 19.1→29.83 (+56%),
C1 adversarial 19.3→26.34 (+37%), C12 draftable 62.8→68.16 (+8.6%),
C12 adversarial 69.1→66.7 (-3.4%). No #26554 crash observed.

### PHASE 2 VERDICT (provisional throughput leader)

| Config | Best verified aggregate | TTFT p50 @ load | Character |
|---|---|---|---|
| **llama.cpp, slots=C, spec off, adversarial C12** | **69.06 (x3)** | 2.6 s | box record |
| llama.cpp, slots=C, spec off, C8 | 67.82 (x3) | ~2.2 s | same plateau, less load |
| llama.cpp + DSpark n3, C12 draftable | 68.16 (x1) | — | best draftable |
| ds4 ship (spec on), C12 | 58.61 (x1) / record 59.89 spec-off (x3) | 1.9-2.8 s | smooth curve |
| ds4, C1 draftable (spec on) | 30.06 | **0.96 s** | interactive king |

- The plan's decision rule ("ds4 must lead by >15%") is REVERSED: llama.cpp
  leads peak aggregate by ~15%. The bake-off re-opens per the rule.
- ds4 retains: TTFT at every load, C1-C8 curve stability without slot
  tuning, ~1000 tok/s community prefill (not yet re-measured here), prefix
  cache/fork-by-copy, disk KV banks — the interactive/agent envelope.
- Honesty checks passed: usage-token accounting both engines; llama.cpp
  wrote SHORTER outputs (~341 vs ~449 tok/req) so its rate is not padding.
- Provisional serving posture: **llama.cpp (slots=C, spec by workload) for
  max-throughput lanes; ds4 for interactive agent serving.** Final selection
  waits on the quality gate (Phase 4) per the reviewed plan.
- Still owed before "record" goes public: quality gate on UD-IQ2_M quant,
  prefill sweep (llama-benchy), 24 h soak, transcript spot-audit.

## 2026-08-09 — llama.cpp VERIFIED: 69.1 tok/s @ C12 (new box record)

3 repeats, CSVs `20260808-194046-...` / `20260808-201200-...` (VERIFY tag).

| Point | median | spread |
|---|---|---|
| C12 adversarial | **69.06** | 0.73 |
| C12 draftable | 62.77 | 0.75 |
| C8 adversarial | 45.96 | 0.14 |
| C8 draftable | 33.06 | 8.36 (unstable) |

Findings:
1. **llama.cpp at C=slots(12) beats ds4's 59.89 record by 15.3%.** Dense
   full-slot batching is llama.cpp's sweet spot; partial occupancy (C8 of 12
   slots) is erratic and much slower than ds4.
2. Length-honesty check from CSVs: llama.cpp averaged ~341 completion
   tokens/request vs ds4 ~449 at C12 adversarial — the higher rate is not
   output padding.
3. ds4 still wins: TTFT (1.9s vs 2.6-4.5s @ C12), C1-C8 latency shape,
   prefill, and curve stability. Serving choice is workload-shaped:
   llama.cpp for saturated batch farms, ds4 for interactive agents.
4. Next probes: --parallel 8 slot-matching at C8; DSpark sidecar lane.

## 2026-08-09 — llama.cpp control sweep (SMOKE, 1 repeat) — VERIFICATION PENDING

Engine: llama.cpp 687e778, UD-IQ2_M, spec off, 12 slots x 32K ctx, fa on.
CSVs: `20260808-185923-llamacpp-687e778-draftable.csv`, `20260808-191853-...adversarial.csv`.

| C | Draftable agg | Adversarial agg | ttft p50 | notes |
|---|---|---|---|---|
| 1 | 19.11 | 19.28 | 0.5-0.7 s | matches community 19.7 single-stream |
| 4 | 39.54 | 22.20 | 1.7-1.9 s | erratic mid-curve |
| 8 | 39.17 | 45.51 | 2.2-3.4 s | erratic mid-curve |
| 12 | 62.61 | **68.25** | 2.6-4.5 s | ABOVE ds4's 59.9 — unverified |

**Caution — do not quote 68.25 yet.** Single repeat; non-monotonic curve;
TTFT much worse than ds4 at same C; and cross-engine token semantics need a
transcript audit (thinking-content handling and output-length distribution
differ per engine — aggregate tok/s rewards longer outputs). Verification
runs (3 repeats C8/C12 both workloads) started 2026-08-09.

## 2026-08-09 — RECORD RUN: spec-off adversarial C8/C12 x3

CSV: `20260808-180530-ds4-v0.5.6-adversarial.csv` (config tag RECORD).

| C | reps | median agg tok/s | spread | power max | throttle |
|---|---|---|---|---|---|
| 8 | 3 | 59.01 | 2.78 (first point cold after restart) | 87 W | none |
| 12 | 3 | **59.89** | **0.87** | 87 W | none |

**Verified record: 59.9 tok/s aggregate @ C12** (ds4 v0.5.6, Q2 ship quant,
DSpark OFF, ctx 32768, adversarial natural-stop workload, 180 s fixed
windows, usage-token accounting). Community reference: 59 @ C12 (spec on,
forced 512-tok completions). Our matching spec-on figure: 58.6.
Takeaway: the "record" delta comes from disabling speculation at high C.

## 2026-08-08 — DSpark on/off A/B (SMOKE, 1 repeat)

Same protocol as baseline; C 1/4/8/12. Spec off via `ds4-serve --no-spec`.
CSVs: `20260808-172605-...draftable.csv`, `20260808-174423-...adversarial.csv`.

| C | Draftable ON→OFF | Adversarial ON→OFF |
|---|---|---|
| 1 | 30.06 → 21.49 (spec **+40%**) | 22.33 → 21.71 (+3%) |
| 4 | 45.91 → 46.38 (wash) | 47.82 → 48.13 (wash) |
| 8 | 56.14 → 56.63 (wash) | 58.07 → 59.68 (off +2.8%) |
| 12 | 55.69 → 56.85 (off +2.1%) | 58.61 → **60.04** (off +2.4%) |

### Findings

1. **New best aggregate: 60.04 tok/s @ C12, adversarial, spec OFF** —
   above the community's published 59 (single repeat; record run pending).
2. DSpark pays only at low concurrency on draftable content (+40% @ C1);
   neutral at C4; small net LOSS at C8-12 (verify cost competes with batching).
3. Production shape: spec ON for interactive/low-C lanes, OFF for batch
   throughput. A per-load toggle (two ports or dynamic) is worth a task.
4. High-C deltas (2-3%) are within single-repeat noise → 3-repeat record
   run decides.

## 2026-08-08 — ds4 v0.5.6 baseline, ship config (SMOKE, 1 repeat)

- Engine: ds4 v0.5.6 (`df641a7`), DSpark drafter on, ctx 32768, ship defaults.
- Server: `ds4-serve --host 0.0.0.0 --port 8000` on spark-381a.
- Harness: agent_bench.py post-T1/T8-T11 fixes; `token_source=usage` on all rows.
- Protocol: 30 s warmup, 180 s fixed window, unique prefixes, temp 1.0,
  top_p 0.95, max_tokens 512, natural stops. Single repeat — smoke grade.
- CSVs: `20260808-163435-ds4-v0.5.6-draftable.csv`,
  `20260808-165616-ds4-v0.5.6-adversarial.csv` (+ earlier 60 s smoke
  `20260808-162805-...`).

| C | Draftable agg tok/s | Adversarial agg tok/s | TTFT p50 | Power max | Temp max | Throttle |
|---|---|---|---|---|---|---|
| 1 | 30.06 | 22.33 | 0.6-1.0 s | 66 W | 71 C | none |
| 2 | 31.14 | 31.89 | ~1.0 s | 88 W | 71 C | none |
| 4 | 45.91 | 47.82 | ~1.0 s | 85 W | 74 C | none |
| 8 | 56.14 | 58.07 | ~1.5 s | 89 W | 77 C | none |
| 12 | 55.69 | 58.61 | 2.4-2.8 s | 81-89 W | 76 C | none |

185 requests, 0 errors.

### Findings

1. **58.6 tok/s aggregate @ C12** on day one vs the fork's published 59
   (theirs: 512-token forced completions; ours: natural agent stops).
2. **Not thermally limited**: peak 89 W of 140 W TDP, 77 C, clocks steady
   2.41-2.48 GHz, zero throttle reasons. Bandwidth-bound as the roofline
   predicted. Clock lock demoted to low priority.
3. **Speculation inverts with load**: C1 draftable +35% over adversarial
   (DSpark wins); C8-12 adversarial slightly ahead (long outputs amortize
   prefill; verify cost competes with batching). Per-load speculation
   tuning is the top Phase 4 experiment.
4. **Knee at C8**: aggregate flat C8→C12 while TTFT p50 rises ~60%.
   Production cap candidate: C8.
5. Installer cold single-stream smoke (short prompt): 22.7 tok/s gen,
   36.6 tok/s prefill — consistent with C1 adversarial.

### Operational notes (feed T26 runbook)

- `ds4-server --dspark` takes the drafter FILE as its argument. Use
  `ds4-serve` (launcher) — it wires model, drafter, and ctx correctly.
- `pkill -f` patterns over SSH must not match the remote command string
  itself (use a `[r]` bracket trick).
- GB10 nvidia-smi reports `[N/A]` for `memory.used` (UMA). Parsers must
  tolerate it; use host `MemAvailable` for memory tracking.

### Next

- [ ] DSpark on/off A/B (same protocol, C 1/4/8/12) — in progress
- [ ] 3-repeat record run at the winning config
- [ ] llama.cpp control build (UD-IQ2_M) + same sweeps
- [ ] T5 security baseline before any always-on serving
