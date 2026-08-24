# Kernel 6.17.0-1031-nvidia on GB10: sustained GPU inference dies with NVRM OOM + ~80 GiB unreclaimable leak on process exit (1029 clean)

**Hardware:** DGX Spark (GB10, sm_121a), 128 GB unified, driver 580.173.02,
CUDA 13.0.88. Reproduced on the box after upgrading via standard apt
(`linux-nvidia-hwe-24.04` 6.17.0-1029.29 → 6.17.0-1031.31).

**Workload:** a native CUDA inference server (Entrpi/ds4, ~81 GiB resident
model in unified memory) under sustained 8-way concurrent decode: fixed
180-second benchmark windows, back to back.

**Symptom on 6.17.0-1031 (3/3 reproductions, including from fresh boot):**
1. First two windows run clean (~56 tok/s aggregate, ~8 GiB free).
2. Mid-third-window: every request errors; dmesg fills with
   `NVRM: nvCheckOkFailedNoLog: Check failed: Out of memory
   [NV_ERR_NO_MEMORY] ... _memdescAllocInternal(pMemDesc) @ mem_desc.c:1359`
3. **After the process is killed, ~80 GiB stays allocated** — no user
   process holds it, `drop_caches` does not return it, only a reboot does.
4. Long-lived processes leak gradually too: a vLLM TP=2 deployment's free
   memory drifted 12 → 4 GiB over ~a day on 1031 (stable for 24 h on 1029).

**One-variable bisect (same box, same binaries, same bench, grub-selected kernel):**

| kernel | 3× consecutive C8 windows | free mem after process kill |
|---|---|---|
| 6.17.0-1031-nvidia | 56.7, 55.7, **died (100% errors)** | 34 GiB (**~81 GiB leaked**) |
| 6.17.0-1029-nvidia | 55.9, 56.0, 56.6 — clean | 115 GiB (fully reclaimed) |

**Why this may be slipping through**: short benchmarks pass — the first
~6 minutes of load look perfect (we initially validated the upgrade with a
short probe and saw a slight improvement). Only the third consecutive
sustained window exposes it.

**Timing note:** 6.17.0-1031 was published to noble-updates on 2026-08-20,
so most GB10 fleets have not taken it yet — this report is intended to land
before the upgrade wave does. Both kernels load the same NVIDIA OPEN kernel
module at 580.173.02; the regression tracks the kernel+module build pair.

**Workaround:** grub-pin 6.17.0-1029 and `apt-mark hold` the
`linux-*-nvidia-hwe-24.04` meta-packages.

Happy to run diagnostics/candidate kernels — the reproducer is scripted and
takes ~25 minutes end to end.
