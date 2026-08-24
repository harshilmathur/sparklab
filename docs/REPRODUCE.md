# Reproduce SparkLab results

Copy-paste path from a fresh DGX Spark (GB10, DGX OS / Ubuntu 24.04) to a
benchmark number. Every version comes from [pins.env](../pins.env) — check it
before you start; docs never restate pins.

## 0. Prerequisites

- DGX Spark with CUDA 13.x driver stack (stock DGX OS).
- 120+ GiB free disk. Network for ~90 GiB of downloads.
- `git`, `python3` (stock). No pip packages needed — the harness is stdlib-only.

## 1. Get the repo

```sh
git clone https://github.com/<user>/sparxlab.git && cd sparxlab
```

## 2. Install the engine (ds4 lane)

The pinned installer builds ds4 and downloads the ship quant (~88 GiB):

```sh
curl -sSL https://raw.githubusercontent.com/entrpi/ds4-on-spark/main/install.sh | bash
```

Verify it matches pins.env (`DS4_REF`) and the GGUF sha256s:

```sh
cd ~/code/ds4 && git describe --tags     # must equal DS4_REF
sha256sum ~/gguf/*.gguf                  # must equal MODEL_SHA256 / DRAFTER_SHA256
```

## 3. Serve

```sh
~/.local/bin/ds4-serve --host 0.0.0.0 --port 8000     # ship config (DSpark on)
# max-throughput config used for the record run:
~/.local/bin/ds4-serve --no-spec --host 0.0.0.0 --port 8000
```

Ready when `curl -sf localhost:8000/v1/models` returns 200.

## 4. Smoke bench (30 seconds)

```sh
python3 bench/agent_bench.py --base-url http://localhost:8000 \
  --model deepseek-v4-flash --engine ds4-$(cd ~/code/ds4 && git describe --tags) \
  --concurrency 1 --warmup-seconds 5 --measure-seconds 30
```

## 5. Record run (the number we publish)

```sh
python3 bench/agent_bench.py --base-url http://localhost:8000 \
  --model deepseek-v4-flash --engine ds4-v0.5.6 \
  --engine-config "dspark=off,ctx=32768,RECORD" \
  --workload adversarial --concurrency 8 12 --repeats 3 \
  --warmup-seconds 30 --measure-seconds 180
```

Compare your CSV against the golden result in `bench/results/`
(`20260808-180530-ds4-v0.5.6-adversarial.csv`): C12 median 59.89 tok/s
aggregate, ±1 tok/s is normal. Protocol details and honest caveats:
[results-log.md](results-log.md).

## Notes that save you an hour

- `token_source` in the CSV must say `usage`. If it says `deltas`, your
  engine does not report usage in streams and numbers are NOT comparable.
- The llama.cpp control lane and its flags are in
  [results-log.md](results-log.md); readiness is `/health` returning 200 —
  a bare TCP answer means "still loading".
- Thermals: the box should never throttle (we never saw >77 C / 89 W). If
  `throttle_seen` is not `none`, your numbers are not comparable.
- Run `python3 bench/test_agent_bench.py` (9 tests) before trusting a
  modified harness.
