# SparkLab — DeepSeek Flash on two DGX Sparks, measured honestly

Ten weeks of benchmarking, tuning, and certification of DeepSeek's Flash models
on NVIDIA DGX Spark (GB10) hardware: first **DeepSeek-V4-Flash-0731** on one box,
then on two boxes joined by a 200 GbE QSFP112 link, and since 2026-10-20
**DeepSeek-V4.1-Flash-1017** as the daily driver. Every number in this repo comes
with its raw CSV, an engine tag, and at least 3 repeats (medians) for record claims.

This is not a serving recipe. The community already has excellent ones (see
[Credits](#credits)). This repo is the **measurement layer**: a benchmark harness
built for agent-shaped workloads, the numbers those recipes produce on real
hardware, and the operational laws we learned the hard way.

## Hardware

| | |
|---|---|
| Boxes | 2× DGX Spark (GB10, 128 GB unified memory, sm_121, aarch64) |
| Measured memory bandwidth | 177–192 GB/s per box (the datasheet says 273) |
| Interconnect | one passive QSFP112 200 GbE DAC, direct, same port on both ends |
| Power | one 600 VA UPS **per box** (one shared UPS cannot carry two under load) |
| Clocks | SM clock capped at 2100 MHz after power resets under peak load (costs <2% decode) |

## Daily driver: DeepSeek-V4.1-Flash-1017 on TensorFold TP2 (since 2026-10-20)

Measured on our own harness: usage-field token counts, 3 repeats, zero errors,
the same two boxes and the same cable as every other number here. Stack:
tonyd2wild's TensorFold TP2 run (EXL3 2.9 bpw weights, DSpark drafting, Engram
tables on local NVMe). The previous driver is in the right-hand column.

| Metric | V4.1-Flash-1017, TensorFold TP2 | V4-Flash-0731, vLLM TP2 |
|---|---|---|
| Single-stream decode, draftable / adversarial corpus | **91.5 / 54.9 tok/s** | 65.8 / 33.4 |
| Peak single-stream (community ruler, best content) | **128.8** (code 94.7, prose ~73) | ~89 (code ~73, prose ~52) |
| Four single-turn streams, aggregate | **221.8 tok/s** | 60.9 at 12 streams |
| Time to first token, single stream | **0.2–0.4 s** | ~0.7 s |
| Quality, our 14-scenario eval, thinking on / off | **98% / 83%** | 88% / 73% |
| Needle retrieval | **found at 992K tokens** (1M window) | found at 1,010,530 |
| Cold prefill | **2,231 tok/s at 127K, 1,618 at 992K** (1M in 613 s) | ~1,800 at 32K, 1,198 at 419K |
| Warm cached prefix, 22.6K tokens | cold 10.2 s, **warm 1.5 s** | seconds |
| Load time | **27 s** | ~15 min |
| Stability | **24 h soak, 112 cycles, 336 windows, 0 failures** (2026-10-27) | 24 h soak, 111 cycles, 0 failures |
| Weights | EXL3 2.9 bpw (quality holds at 98%) | official FP8, unquantized |

Caveats, stated plainly: the engine is days old (a new Zig TensorFold branch);
multi-turn closed-loop aggregate is bound by per-turn prefill (the prefix cache
is page-granular); thinking is a per-request string knob (`reasoning_effort:
"high"`, the integer form is rejected). A 24 h soak completed clean on 2026-10-27
(112 cycles, 336 windows, 0 failures; single-stream medians held). The bring-up
notes and the fixes we needed (head self-ssh over the fabric, the pack's chat
template, Engram locality) are in [docs/RESULTS-LOG.md](docs/RESULTS-LOG.md) and
[docs/RUNBOOK-DSV41-DRIVER.md](docs/RUNBOOK-DSV41-DRIVER.md).

## V4-Flash-0731: certified numbers (2026-08-24)

These stand as the V4 record book and remain the fallback configuration.

| Metric | Value | Configuration |
|---|---|---|
| Single-stream decode, peak | **~89 tok/s** | TP=2, best-case draftable content, warmed, decode-only (community ruler) |
| Single-stream decode, realistic | ~70–73 tok/s | TP=2, real code generation |
| Single-stream decode, certified | **65.8 tok/s** | median of 3 across a mixed draftable corpus, closed-loop (our stricter ruler) |
| Peak aggregate | **136.5 tok/s** | two independent replicas, 12 streams each, 2-bit quant |
| TP=2 aggregate | 60.9 tok/s | 12 streams, after OS tuning |
| One-box aggregate | 69.1 tok/s | llama.cpp, slots = concurrency, speculation off |
| One-box single stream | 54.1 tok/s | EXL3 ~2-bit, tuned CUDA-graph captures |
| Warm prefill at 32K | ~2,600 tok/s | TP=2 (cold first touch is 30–60% slower) |
| Context | **1,010,530 tokens retrieved** | TP=2, `nvfp4_ds_mla` KV cache, 6/6 needle ladder |
| Quality | **88%** structured-task eval | TP=2, unquantized, per-request thinking (DeepSeek API: 86%) |
| Stability | 24 h soak, 111 cycles, 0 serving failures | survived a mid-soak kernel upgrade |

> **Two rulers, both honest.** Single-stream decode is driven by speculative
> decoding acceptance, so the headline swings with content and measurement. A
> highly predictable output hits ~89 tok/s (community methodology: warmed,
> `ignore_eos`, decode-only, best content); realistic code lands at ~70–73; our
> closed-loop median across a mixed corpus is 65.8. We publish all three.
> `bench/peak_c1.py` reproduces the peak; the corpus median is the one we defend.

## What else we tested

Same harness, same boxes, so the numbers compare. Details and verdicts are in the
results log.

| Model and stack | Verdict |
|---|---|
| Qwen3.8-Flash-Next, SGLang TP2 (NVFP4) | Quality 98% on our eval and the best prefill of the V4 era, but single stream 25–47 tok/s. Kept as a switchable quality arm. |
| GLM-5.3-Flash, two stacks (EXL3 and NVFP4) | Both died on our boxes with the same silent rank death; reporters who boot it run an older kernel. Parked. |
| DeepSeek-V4-Flash-Vision-Exp, vLLM TP2 | Wedged at boot even with a byte-identical fabric environment. Parked. |
| DeepSeek-V4.1-Flash-1017, TensorFold TP2 | Adopted as the daily driver (table above). |

## The laws (what we learned the hard way)

The distilled findings that transfer to any GB10 deployment are in
**[docs/LAWS.md](docs/LAWS.md)**. Highlights:

- **Kernel warning (2026-08-24)**: `6.17.0-1031-nvidia` kills sustained GPU
  inference on GB10 (dies on the 3rd consecutive 8-way window, NVRM
  `NV_ERR_NO_MEMORY`) and leaks ~80 GiB on engine death. Bisect-proven against
  1029 on identical everything. Pin 1029 and hold the kernel meta-packages.
- **The AC-cycle law**: after any QSFP or PCIe hardware change, power-cycle both
  boxes with the cords out. Stale PCIe state cost us 7.9× NCCL bandwidth and half
  of single-stream decode; warm reboots do not clear it.
- **Speculation is lossless but workload-shaped**: +40–56% at one stream on
  draft-friendly output, a wash by four streams; zero quality cost (A/B verified).
- **The thinking switch**: thinking-capable checkpoints served with thinking off
  lose strict-format compliance (73% to 88% on our eval with per-request thinking).
- **UVM over-commit is a livelock, not an OOM**: keep utilization at or below
  0.92 and 10–15 GiB free, or the box hangs with no log and no OOM killer.
- **Cross-engine tok/s comparisons need `usage`-field token accounting on both
  sides**, and closed-loop fixed-window aggregates are not comparable to
  server-side decode-window rates (most community numbers are the latter; they
  read ~2.5× higher on identical hardware).
- **Download laws**: one box downloads from the internet, the other gets files
  over the DAC (we hit a 3 TB ISP cap); large files beside a loaded engine need a
  page-cache drop loop; Xet-only files over 10 GB go through `scripts/pget.py`.
- **Experiment windows run under an on-box supervisor** that restores the driver
  on failure, and every health verdict checks the served model name, not just the
  port. Both rules came from outages.

## The harness

`bench/agent_bench.py` is a dependency-free (stdlib-only) serving benchmark built
for agent-shaped traffic rather than fixed-length generation:

- closed-loop sessions, fixed measurement windows, warmup excluded
- **token counts from the server's `usage` field**, never client-side guesses
- two corpora: `draftable` (tool calls, JSON, SQL, code) and `adversarial`
  (open prose), because speculation makes any single number a lie
- TTFT and inter-token percentiles, GPU power, temperature and clock sampling,
  the full configuration in every CSV row

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

Also here: `quality_eval.py` (14 structured-output scenarios), `longctx_probe.py`
(needle ladder with usage-exact depths), `warm_prefix_probe.py` (prefix-cache
verification), `peak_c1.py` (peak decode-rate probe, community methodology),
`soak.sh` (24 h mixed load), `scripts/pget.py` (parallel ranged downloader with
per-chunk resume), `scripts/eval-supervisor.sh` (on-box experiment supervisor
with automatic driver restore), `scripts/os-tune-spark.sh` (GB10 OS tuning).
Run `python3 bench/test_agent_bench.py` before trusting any harness change.

## Layout

| Path | What it is |
|---|---|
| [bench/](bench/) | the harness, the workloads, and **every raw result CSV** |
| [docs/RESULTS-LOG.md](docs/RESULTS-LOG.md) | the full dated log: records, failures, bisects, dead ends (newest first) |
| [docs/LAWS.md](docs/LAWS.md) | distilled operational and performance laws |
| [docs/RUNBOOK-DSV41-DRIVER.md](docs/RUNBOOK-DSV41-DRIVER.md) | start, stop, thinking knob, and fallback for the V4.1 driver |
| [docs/REPRODUCE.md](docs/REPRODUCE.md) | reproduction guide |
| [scripts/](scripts/) | OS tuning, the experiment supervisor, the ranged downloader |
| [pins.env](pins.env) | every version pin in one file (docs never restate them) |

## Credits

This work stands on the community's serving recipes and findings:
[tonyd2wild](https://github.com/tonyd2wild) (the V4.1 TensorFold TP2 run we adopted,
and Patch 4/5 for V4),
[bertholomus](https://github.com/bertholomus) (the TensorFold `dsv41` family and kit),
[LibertAI](https://huggingface.co/LibertAIDAI) (the V4.1 EXL3 2.9 bpw pack),
[MiaAI-Lab](https://github.com/MiaAI-Lab) (the 2× DGX DeepSeek recipe, sparkDash),
[Anemll/dspark-vllm-gx10](https://github.com/Anemll/dspark-vllm-gx10),
[eugr/spark-vllm-docker](https://github.com/eugr/spark-vllm-docker),
[hazyumps/deepseek-v4-flash-gb10](https://github.com/hazyumps/deepseek-v4-flash-gb10),
[Entrpi/ds4](https://github.com/Entrpi/ds4),
[0xSero](https://github.com/0xSero) / [tpurtell](https://github.com/tpurtell) (EXL3 lanes),
[trenchnotes.blog](https://trenchnotes.blog/post/os-optimizations-dgx-spark) (OS tuning),
jasl (SM12x vLLM enablement), and the NVIDIA DGX Spark forum regulars whose threads
answered questions we did not know we had. Models: DeepSeek.

## License

MIT for everything in this repository. Model weights, engines, and container images
are separate works under their own licenses.
