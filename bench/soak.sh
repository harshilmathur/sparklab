#!/usr/bin/env bash
# 24h mixed-load soak. Alternates light/heavy agent-bench cycles against a
# running endpoint; telemetry rides on the Grafana pipeline; failures logged.
# Usage: ./soak.sh <base-url> <model> <engine-tag> [hours]
set -uo pipefail
BASE_URL="${1:?base-url}"; MODEL="${2:?model}"; ENGINE="${3:?engine}"; HOURS="${4:-24}"
HERE="$(cd "$(dirname "$0")" && pwd)"
END=$(( $(date +%s) + HOURS*3600 ))
LOG="$HERE/results/soak-$(date -u +%Y%m%d-%H%M%S)-${ENGINE}.log"
CYCLE=0
echo "soak start $(date -u) engine=$ENGINE hours=$HOURS" | tee "$LOG"
while [ "$(date +%s)" -lt "$END" ]; do
  CYCLE=$((CYCLE+1))
  for CFG in "1 120" "8 300" "4 180"; do
    set -- $CFG
    C=$1; SECS=$2
    W=$([ $((CYCLE % 2)) -eq 0 ] && echo adversarial || echo draftable)
    if ! python3 "$HERE/agent_bench.py" --base-url "$BASE_URL" --model "$MODEL" \
        --engine "$ENGINE" --engine-config "SOAK-cycle$CYCLE" \
        --workload "$W" --concurrency "$C" \
        --warmup-seconds 5 --measure-seconds "$SECS" \
        --outdir "$HERE/results/soak" >>"$LOG" 2>&1; then
      echo "SOAK FAILURE cycle=$CYCLE c=$C w=$W at $(date -u)" | tee -a "$LOG"
    fi
    sleep 30   # idle gap — real traffic breathes
  done
done
FAILS=$(grep -c "SOAK FAILURE" "$LOG" || true)
echo "soak done $(date -u): $CYCLE cycles, $FAILS failures" | tee -a "$LOG"
[ "$FAILS" -eq 0 ]
