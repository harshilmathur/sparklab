#!/usr/bin/env bash
# Standard llama-benchy sweep against a running engine.
# Usage: ./run_bench.sh <base-url> <model-name> <engine-tag> [extra llama-benchy args]
# Auth: set AGENT_BENCH_API_KEY (or OPENAI_API_KEY) to send a bearer token.
set -euo pipefail
BASE_URL="${1:?base-url}"; MODEL="${2:?model}"; ENGINE="${3:?engine tag}"; shift 3 || true

HERE="$(cd "$(dirname "$0")" && pwd)"
# Pin the measuring instrument (see pins.env: LLAMA_BENCHY_COMMIT)
PINS="$HERE/../pins.env"
LLAMA_BENCHY_COMMIT="$(grep -E '^LLAMA_BENCHY_COMMIT=' "$PINS" | cut -d= -f2)"
[ -n "$LLAMA_BENCHY_COMMIT" ] || { echo "error: LLAMA_BENCHY_COMMIT missing from pins.env" >&2; exit 1; }

mkdir -p "$HERE/results"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
OUT="$HERE/results/${STAMP}-${ENGINE}-benchy.txt"

API_KEY="${AGENT_BENCH_API_KEY:-${OPENAI_API_KEY:-}}"
EXTRA_AUTH=()
[ -n "$API_KEY" ] && EXTRA_AUTH=(--api-key "$API_KEY")

{
  echo "# engine=${ENGINE} model=${MODEL} base_url=${BASE_URL}"
  echo "# repo_git=$(git -C "$HERE/.." rev-parse --short HEAD 2>/dev/null || echo n/a) date=${STAMP}"
  echo "# llama_benchy_commit=${LLAMA_BENCHY_COMMIT}"
  uvx --from "git+https://github.com/eugr/llama-benchy@${LLAMA_BENCHY_COMMIT}" llama-benchy \
    --base-url "${BASE_URL}" --model "${MODEL}" \
    --pp 2048 --tg 32 128 512 --depth 0 4096 16384 65536 \
    --latency-mode generation ${EXTRA_AUTH[@]+"${EXTRA_AUTH[@]}"} "$@"
} | tee "${OUT}"
echo "saved -> ${OUT}"
