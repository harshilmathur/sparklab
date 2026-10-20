# Runbook: DeepSeek-V4.1-Flash-1017 daily driver (TensorFold TP2) — since 2026-10-20

Lane dir on BOTH nodes: `/var/tmp/tf1017-tp2` (engine-bin, kit, model, cache, logs, scripts);
Engram tables at `/var/tmp/tf1017/engram` on both. Config: `config.tp2.env` (our fabric:
<lan-ip>/11, HCA rocep1s0f1,roceP2p1s0f1, NET_IF enp1s0f1np1, port 8888).
Served name `deepseek-v4.1-flash`. Pins: pins.env `DSV41_*`.

## Start / stop / status (run on spark1)
    DSV41_CONFIG=/var/tmp/tf1017-tp2/config.tp2.env bash /var/tmp/tf1017-tp2/start_tp2.sh   # precheck + both ranks (~1 min; loads in 27 s)
    DSV41_CONFIG=/var/tmp/tf1017-tp2/config.tp2.env bash /var/tmp/tf1017-tp2/serve_tp2.sh stop
    curl -s localhost:8888/v1/models | grep -o deepseek-v4.1-flash
Logs: `/var/tmp/tf1017-tp2/logs/tp2-lane.log` on each node.

## Thinking
Off by default (speed). Per request: `"reasoning_effort": "high"` (string; the integer form returns 400)
or `chat_template_kwargs: {"thinking": true}`. Quality: 98% with thinking, 83% without.

## Rules
- Precheck needs >= 108 GiB free on both nodes: stop anything else first; drop caches.
- Watchdog (donna) auto-restarts this lane after 3 down-ticks (1/hr). Pause it for experiments
  with `touch /tmp/watchdog-pause` on spark1 (3 h TTL; refresh for longer windows).
- Both ranks must have LOCAL Engram shards; never serve them over NFS.
- Rank caches are tied to the pack revision: a new pack means `inputs_tp2.sh` again (~12 min, no GPU).

## Fallback: restore DS4F-0731 (Mia vLLM TP=2)
    DSV41_CONFIG=/var/tmp/tf1017-tp2/config.tp2.env bash /var/tmp/tf1017-tp2/serve_tp2.sh stop
    ssh spark2 'docker ps -aq | xargs -r docker rm -f'; docker ps -aq | xargs -r docker rm -f
    cd ~/tools/mia-dspark-2x && ./start-deepseek-v4-flash-dspark.sh --host 0.0.0.0   # ~15 min
Then re-point bench/mini/watchdog.sh + nightly_smoke.sh back (git history 2026-10-20) and redeploy to donna.
