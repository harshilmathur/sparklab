# SparkLab — DeepSeek Flash on 1-2 DGX Sparks, measured honestly

Three weeks of systematic benchmarking, tuning, and certification of
**DeepSeek-V4-Flash-0731** on NVIDIA DGX Spark (GB10) hardware — one box,
then two joined by a 200 GbE QSFP112 link. Every number in this repo comes
with its raw CSV, an engine tag, and ≥3 repeats (medians) for record claims.

This is not a serving recipe — the community already has excellent ones (see
[Credits](#credits)). It is the **measurement layer**: a benchmark harness
built for agent-shaped workloads, the certified numbers those recipes produce
on real hardware, and the operational laws we learned the hard way.

## Hardware

| | |
|---|---|
| Boxes | 2× DGX Spark (GB10, 128 GB unified, sm_121, aarch64) |
| Measured bandwidth | 177–192 GB/s per box (not the 273 datasheet) |
| Interconnect | one passive QSFP112 200 GbE DAC, direct, same port both ends |
| Power | one 600 VA UPS **per box** (one shared UPS cannot carry two under load) |

## Daily driver since 2026-10-20: DeepSeek-V4.1-Flash-1017 on TensorFold TP2

Measured on our own harness (usage-field tokens, 3 repeats, zero errors), same two boxes, same cable.
Stack: tonyd2wild's TensorFold TP2 run (EXL3 2.9 bpw, DSpark drafts, Engram tables on local NVMe).

| Metric | V4.1-Flash-1017 (TensorFold TP2) | V4-Flash-0731 (vLLM TP2, previous driver) |
|---|---|---|
| C1 decode, draftable / adversarial | **91.5 / 54.9 tok/s** | 65.8 / 33.4 |
| Peak C1 (community ruler, best content) | **128.8** (code 94.7, prose ~73) | ~89 (code ~73, prose ~52) |
| 4 single-turn streams, aggregate | **221.8 tok/s** | 60.9 at C12 |
| TTFT, single stream | **0.2-0.4 s** | ~0.7 s |
| Quality (our 14-scenario eval), thinking on / off | **98% / 83%** | 88% / 73% |
| Needle retrieval | **found at 992K** (1M window) | 1,010,530 |
| Cold prefill | **2,231 tok/s @127K -> 1,618 @992K** (1M in 613 s) | ~1,800 @32K -> 1,198 @419K |
| Warm cached prefix (22.6K) | cold 10.2 s -> **1.5 s** | seconds |
| Load time | **27 s** | ~15 min |
| Weights | EXL3 2.9 bpw (quality holds) | official FP8, unquantized |

Honest caveats: the engine is days old (a new Zig TensorFold branch); the multi-turn closed-loop
aggregate is prefill-bound per turn (page-granular prefix cache); thinking is a per-request string
knob (`reasoning_effort: "high"`). Bring-up notes and the fixes we needed (fabric self-ssh, the pack's
chat template, Engram locality) are in [docs/RESULTS-LOG.md](docs/RESULTS-LOG.md) and
[docs/RUNBOOK-DSV41-DRIVER.md](docs/RUNBOOK-DSV41-DRIVER.md). Credit: tonyd2wild, bertholomus
(TensorFold dsv41 family), LibertAI (EXL3 pack), MiaAI-Lab.

## V4-Flash-0731 certified numbers (2026-08-24)

| Metric | Value | Configuration |
|---|---|---|
| Single-stream decode (C1), peak | **~89 tok/s** | TP=2, best-case draftable content, warmed, decode-only (community ruler) |
| Single-stream decode (C1), realistic | ~70–73 tok/s | TP=2, real code generation |
| Single-stream decode (C1), certified | **65.8 tok/s** | median-of-3 across a mixed draftable corpus, closed-loop (our stricter ruler) |
| Peak aggregate | **136.5 tok/s** | two independent replicas, 12 streams each |
| TP=2 aggregate | 60.9 tok/s | C12, post OS-tune (seqs-12 ceiling; C8 underfeeds it) |
| One-box aggregate | 69.1 tok/s | llama.cpp, slots = concurrency, spec off |
| One-box C1 | 54.1 tok/s | EXL3 ~2-bit, tuned CUDA-graph captures |
| Warm prefill @32K | ~2,600 tok/s | TP=2 (cold first-touch is 30–60% slower) |
| Context | **1,010,530 tokens retrieved** | TP=2, `nvfp4_ds_mla` KV, 6/6 needle ladder |
| Quality | **88%** structured-task eval | TP=2 unquantized + per-request thinking (API reference: 86%) |
| Stability | 24 h soak, 111 cycles, 0 serving failures | survived a mid-soak kernel upgrade |

> **Two rulers, both honest.** Single-stream decode is entirely
> speculative-decoding-acceptance-driven, so the headline number swings with
> content and measurement. A highly predictable output hits ~89 tok/s
> (community methodology: warmed, `ignore_eos`, decode-only, best content);
> realistic code lands ~70–73; our conservative closed-loop median across a
> mixed corpus is 65.8. We publish all three. `bench/peak_c1.py` reproduces
> the peak; the corpus median is the one we defend.

Full history with method, failures, and dead ends: [docs/RESULTS-LOG.md](docs/RESULTS-LOG.md)
(newest first — the honest version, including everything that did not work).

## The laws (what we learned the hard way)

The distilled findings that transfer to any GB10 deployment:
**[docs/LAWS.md](docs/LAWS.md)**. Highlights:

- **KERNEL WARNING (2026-08-24)**: `6.17.0-1031-nvidia` (published to
  noble-updates 2026-08-20) kills sustained GPU inference on GB10 (dies on
  the 3rd consecutive 8-way window, NVRM `NV_ERR_NO_MEMORY`) and leaks
  ~80 GiB on engine death — reboot-only reclaim. Bisect-proven vs 1029 on
  identical everything. Pin 1029 and hold the kernel meta-packages.
- **The AC-cycle law**: after any QSFP/PCIe hardware change, hard power-cycle
  (cords out) both boxes. Stale PCIe state silently cost us 7.9× NCCL bandwidth
  and half of single-stream decode; warm reboots do not clear it.
- **Speculation is quality-lossless but workload-shaped**: +40–56% at C1 on
  draft-friendly output, a wash by C4; zero quality cost (A/B verified twice).
- **The thinking switch**: on thinking-capable checkpoints served with
  thinking off, strict-format compliance drops hard (73% → 88% on our eval
  with per-request `chat_template_kwargs: {"thinking": true}`).
- **UVM over-commit is a livelock, not an OOM**: keep utilization ≤0.92 and
  10–15 GiB free, or the box hard-hangs with no log and no OOM-killer.
- **Cross-engine tok/s comparisons are only valid with `usage`-field token
  accounting on both sides** — and closed-loop fixed-window aggregates are
  not comparable to server-side decode-window rates (most community numbers
  are the latter; they read ~2.5× higher on identical hardware).

## The harness

`bench/agent_bench.py` — a dependency-free (stdlib-only) serving benchmark
built for agent-shaped traffic rather than fixed-length generation:

- closed-loop sessions, fixed measurement windows, warmup excluded
- **token counts from the server's `usage` field**, never client-side guesses
- two corpora: `draftable` (tool calls, JSON, SQL, code) and `adversarial`
  (open prose) — speculation makes one number a lie
- TTFT/ITL percentiles, GPU power/temp/clock sampling, full config in every CSV row

```sh
# smoke (1 point, short window)
python3 bench/agent_bench.py --base-url http://HOST:PORT \
  --model MODEL --engine my-engine-tag \
  --concurrency 1 --warmup-seconds 5 --measure-seconds 30

# record grade (both workloads, 3 repeats)
python3 bench/agent_bench.py --base-url http://HOST:PORT \
  --model MODEL --engine my-engine-tag \
  --workload draftable --concurrency 1 8 --repeats 3
```

Also here: `quality_eval.py` (14 structured-output scenarios),
`longctx_probe.py` (needle ladder with usage-exact depths),
`warm_prefix_probe.py` (prefix-cache verification), `peak_c1.py` (peak decode-rate probe, community methodology), `soak.sh` (24 h mixed load); `scripts/pget.py` (parallel ranged downloader for Xet-only files), `scripts/eval-supervisor.sh` (on-box experiment supervisor with auto-restore).
Run `python3 bench/test_agent_bench.py` before trusting any harness change.

## Layout

| Path | What it is |
|---|---|
| [bench/](bench/) | the harness + workloads + **every raw result CSV** |
| [docs/RESULTS-LOG.md](docs/RESULTS-LOG.md) | the full dated log — records, failures, bisects, dead ends |
| [docs/LAWS.md](docs/LAWS.md) | distilled operational + performance laws |
| [docs/REPRODUCE.md](docs/REPRODUCE.md) | reproduction guide |
| [scripts/os-tune-spark.sh](scripts/os-tune-spark.sh) | GB10 OS tuning (headless, core/IRQ pinning, swap) — credit: trenchnotes.blog |
| [pins.env](pins.env) | every version pin in one file (docs never restate them) |

## Credits

This work stands on the community's serving recipes and findings:
[eugr/spark-vllm-docker](https://github.com/eugr/spark-vllm-docker),
[MiaAI-Lab](https://github.com/MiaAI-Lab) (2× DGX recipe, sparkDash),
[Anemll/dspark-vllm-gx10](https://github.com/Anemll/dspark-vllm-gx10),
[hazyumps/deepseek-v4-flash-gb10](https://github.com/hazyumps/deepseek-v4-flash-gb10),
[tonyd2wild](https://github.com/tonyd2wild) (Patch 4/5),
[Entrpi/ds4](https://github.com/Entrpi/ds4),
[0xSero](https://github.com/0xSero) / [tpurtell](https://github.com/tpurtell) (EXL3 lanes),
jasl (SM12x vLLM enablement), and the NVIDIA DGX Spark forum regulars whose
threads answered questions we didn't know we had. Model: DeepSeek.

## License

MIT for everything in this repository. Model weights, engines, and container
images are separate works under their own licenses.
