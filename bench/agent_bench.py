#!/usr/bin/env python3
"""Agent-shaped concurrency benchmark for OpenAI-compatible endpoints.

Measurement contract (post eng-review, tasks T1/T8/T9/T10/T11/T15/T18/T21):
- Tokens come from the final `usage` chunk (stream_options.include_usage).
  Fallback: SSE delta count, flagged in the `token_source` column.
- Fixed window: only tokens timestamped inside [t_start, t_start+measure]
  count toward aggregate tok/s. Streams past the deadline are abandoned.
- Decode rate (tokens/sec between first and last token) is reported
  separately from wall-clock throughput, which includes TTFT.
- Errors: zero-token responses are errors; retries back off exponentially;
  the process exits non-zero if any point produced zero successes.
- Telemetry: a background thread samples nvidia-smi every 5s during the
  window; max/mean power, max temp, clock range, throttle reasons.

Stdlib only. No dependencies.
"""

import argparse
import asyncio
import concurrent.futures
import csv
import hashlib
import json
import os
import random
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

ERROR_ROW_CAP = 100          # per point, keep memory bounded on crash loops
BACKOFF_START_S = 0.5
BACKOFF_MAX_S = 8.0
MIN_TOK_RATE = 3.0           # tok/s floor used for the per-request wall cap
MIN_SAMPLES_FOR_P95 = 10


def grafana_annotate(text: str, tags: list[str], t_start_ms: int, t_end_ms: int | None = None):
    """Post a region annotation to Grafana if GRAFANA_URL + GRAFANA_SA_TOKEN are set. Silent no-op otherwise."""
    url = os.environ.get("GRAFANA_URL")
    tok = os.environ.get("GRAFANA_SA_TOKEN")
    if not url or not tok:
        return
    body = {"text": text, "tags": tags, "time": t_start_ms}
    if t_end_ms:
        body["timeEnd"] = t_end_ms
    req = urllib.request.Request(url.rstrip("/") + "/api/annotations",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {tok}"})
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except Exception:
        pass  # monitoring is best-effort; never fail a bench over it


def load_prompts(workload: str) -> list[str]:
    d = Path(workload)
    if not d.is_dir():
        d = HERE / "workloads" / workload
    prompts = [f.read_text() for f in sorted(d.glob("*.txt"))]
    if not prompts:
        raise SystemExit(f"error: no .txt prompts in {d} — pass a workload name or a directory path")
    return prompts


def auth_headers(api_key: str | None) -> dict:
    h = {"Content-Type": "application/json"}
    if api_key:
        h["Authorization"] = f"Bearer {api_key}"
    return h


def preflight(base_url: str, api_key: str | None) -> str:
    """Verify the endpoint answers /models; normalize a missing /v1. Exit loudly if dead."""
    candidates = [base_url.rstrip("/")]
    if not candidates[0].endswith("/v1"):
        candidates.append(candidates[0] + "/v1")
    last_err = None
    for base in candidates:
        req = urllib.request.Request(base + "/models", headers=auth_headers(api_key))
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                if r.status == 200:
                    return base
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            last_err = e
    raise SystemExit(
        f"error: endpoint preflight failed for {candidates} — {last_err}\n"
        f"fix: is the server running? does --base-url include the right host/port?"
        f" if auth is enabled, pass --api-key or set AGENT_BENCH_API_KEY."
    )


class GpuSampler:
    """Samples nvidia-smi (locally or over ssh) every interval during a window."""

    QUERY = ("--query-gpu=power.draw,temperature.gpu,memory.used,"
             "clocks.sm,clocks_throttle_reasons.active",
             "--format=csv,noheader,nounits")

    def __init__(self, ssh_host: str | None, interval_s: float = 5.0):
        self.ssh_host = ssh_host
        self.interval = interval_s
        self.samples: list[dict] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _sample_once(self) -> dict | None:
        cmd = ["nvidia-smi", *self.QUERY]
        if self.ssh_host:
            cmd = ["ssh", "--", self.ssh_host, "nvidia-smi", *self.QUERY]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            parts = [x.strip() for x in out.stdout.strip().split(",")]
            if len(parts) < 5:
                return None

            def num(s):
                try:
                    return float(s)
                except ValueError:  # "[N/A]" on UMA fields (GB10 memory.used)
                    return float("nan")

            return {"power": num(parts[0]), "temp": num(parts[1]),
                    "mem": num(parts[2]), "sm_clock": num(parts[3]),
                    "throttle": parts[4]}
        except Exception:
            return None

    def _run(self):
        while not self._stop.is_set():
            s = self._sample_once()
            if s:
                self.samples.append(s)
            self._stop.wait(self.interval)

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> dict:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=20)
        if not self.samples:
            return {"power_w_max": "", "power_w_mean": "", "temp_c_max": "",
                    "mem_used_mib_max": "", "sm_clock_min": "", "sm_clock_max": "",
                    "throttle_seen": "", "gpu_samples": 0}
        throttles = {s["throttle"] for s in self.samples
                     if s["throttle"] and s["throttle"] not in ("[N/A]", "0x0000000000000000")}

        def agg(field, fn):
            vals = [s[field] for s in self.samples if s[field] == s[field]]  # drop NaN
            return round(fn(vals), 1) if vals else ""

        return {
            "power_w_max": agg("power", max),
            "power_w_mean": agg("power", statistics.mean),
            "temp_c_max": agg("temp", max),
            "mem_used_mib_max": agg("mem", max),
            "sm_clock_min": agg("sm_clock", min),
            "sm_clock_max": agg("sm_clock", max),
            "throttle_seen": ";".join(sorted(throttles)) if throttles else "none",
            "gpu_samples": len(self.samples),
        }


def stream_request(base_url, model, prompt, max_tokens, temperature, top_p,
                   api_key, wall_cap_ts):
    """Blocking SSE request. Returns a result dict. Runs inside the pool."""
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "stream": True,
        "stream_options": {"include_usage": True},
    }).encode()
    req = urllib.request.Request(base_url + "/chat/completions", data=body,
                                 headers=auth_headers(api_key))
    t0 = time.monotonic()
    tok_times: list[float] = []
    usage_tokens = None
    delta_count = 0
    skipped_lines = 0
    truncated = False
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            for raw in r:
                now = time.monotonic()
                if now > wall_cap_ts:
                    truncated = True
                    break
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                if not line.startswith("data:"):
                    skipped_lines += 1
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    obj = json.loads(payload)
                except json.JSONDecodeError:
                    skipped_lines += 1
                    continue
                usage = obj.get("usage")
                if usage and usage.get("completion_tokens") is not None:
                    usage_tokens = usage
                choices = obj.get("choices") or []
                if choices:
                    delta = choices[0].get("delta") or {}
                    if delta.get("content") or delta.get("reasoning_content"):
                        tok_times.append(now)
                        delta_count += 1
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"[:300],
                "t0": t0, "t1": time.monotonic()}
    t1 = time.monotonic()
    if usage_tokens is not None:
        ntok = int(usage_tokens.get("completion_tokens") or 0)
        prompt_tokens = int(usage_tokens.get("prompt_tokens") or 0)
        token_source = "usage"
    else:
        ntok = delta_count
        prompt_tokens = 0
        token_source = "deltas"
    if ntok <= 0 or not tok_times:
        return {"ok": False, "error": "zero tokens generated (empty or non-stream response)",
                "t0": t0, "t1": t1}
    ttft = tok_times[0] - t0
    decode_s = tok_times[-1] - tok_times[0]
    itl = (statistics.median(b - a for a, b in zip(tok_times, tok_times[1:]))
           if len(tok_times) > 1 else None)
    return {
        "ok": True, "t0": t0, "t1": t1, "ttft_s": ttft, "itl_s": itl,
        "gen_tokens": ntok, "prompt_tokens": prompt_tokens,
        "token_source": token_source, "skipped_lines": skipped_lines,
        "truncated": truncated, "tok_times": tok_times,
        "decode_tok_s": (ntok - 1) / decode_s if decode_s > 0 and ntok > 1 else None,
        "prefill_tok_s": prompt_tokens / ttft if prompt_tokens and ttft > 0 else None,
    }


async def one_session(session_id, pool, args, base_url, prompts, deadline,
                      window_end, results, errors, counting):
    rng = random.Random(1234 + session_id)
    loop = asyncio.get_running_loop()
    backoff = BACKOFF_START_S
    while time.monotonic() < deadline:
        prompt = rng.choice(prompts)
        nonce = f"[session {session_id} run {rng.randint(0, 10**9)}] "
        wall_cap = deadline + args.max_tokens / MIN_TOK_RATE
        res = await loop.run_in_executor(
            pool, stream_request, base_url, args.model, nonce + prompt,
            args.max_tokens, args.temperature, args.top_p, args.api_key, wall_cap)
        if not res["ok"]:
            if counting and len(errors) < ERROR_ROW_CAP:
                errors.append({"ts": datetime.now(timezone.utc).isoformat(),
                               "session": session_id, "error": res["error"],
                               "prompt_sha": hashlib.sha256(prompt.encode()).hexdigest()[:12]})
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX_S)
            continue
        backoff = BACKOFF_START_S
        if counting:
            res["tokens_in_window"] = sum(1 for t in res.pop("tok_times") if t <= window_end)
            results.append(res)
        else:
            res.pop("tok_times", None)


async def run_point(concurrency, args, base_url, prompts):
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=concurrency + 4)
    try:
        if args.warmup_seconds > 0:
            warm_end = time.monotonic() + args.warmup_seconds
            await asyncio.gather(*[
                one_session(900 + i, pool, args, base_url, prompts, warm_end,
                            warm_end, [], [], counting=False)
                for i in range(concurrency)])
        results: list[dict] = []
        errors: list[dict] = []
        sampler = GpuSampler(args.gpu_ssh_host or None)
        sampler.start()
        t_start = time.monotonic()
        deadline = t_start + args.measure_seconds
        await asyncio.gather(*[
            one_session(i, pool, args, base_url, prompts, deadline, deadline,
                        results, errors, counting=True)
            for i in range(concurrency)])
        gpu = sampler.stop()
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    ok = results
    window_tokens = sum(r["tokens_in_window"] for r in ok)
    agg = window_tokens / args.measure_seconds
    ttfts = [r["ttft_s"] for r in ok]
    itls = [r["itl_s"] for r in ok if r["itl_s"] is not None]
    decode = [r["decode_tok_s"] for r in ok if r["decode_tok_s"]]
    prefill = [r["prefill_tok_s"] for r in ok if r["prefill_tok_s"]]
    n = len(ttfts)
    p95 = ""
    if n >= MIN_SAMPLES_FOR_P95:
        s = sorted(ttfts)
        k = 0.95 * (n - 1)
        f = int(k)
        p95 = round(1000 * (s[f] + (s[min(f + 1, n - 1)] - s[f]) * (k - f)), 0)
    point = {
        "concurrency": concurrency,
        "requests_ok": len(ok),
        "requests_err": len(errors),
        "first_error_ts": errors[0]["ts"] if errors else "",
        "tokens_in_window": window_tokens,
        "window_s": args.measure_seconds,
        "aggregate_tok_s": round(agg, 2),
        "decode_tok_s_median": round(statistics.median(decode), 2) if decode else "",
        "prefill_tok_s_median": round(statistics.median(prefill), 2) if prefill else "",
        "per_stream_wall_tok_s_median": round(statistics.median(
            r["gen_tokens"] / (r["t1"] - r["t0"]) for r in ok), 2) if ok else "",
        "ttft_p50_ms": round(1000 * statistics.median(ttfts), 0) if ttfts else "",
        "ttft_p95_ms": p95,
        "ttft_samples": n,
        "itl_p50_ms": round(1000 * statistics.median(itls), 1) if itls else "",
        "token_source": (ok[0]["token_source"] if ok else ""),
        "skipped_sse_lines": sum(r["skipped_lines"] for r in ok),
        "truncated_streams": sum(1 for r in ok if r["truncated"]),
    }
    point.update(gpu)
    return point, errors


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True, help="endpoint origin, with or without /v1")
    ap.add_argument("--model", required=True)
    ap.add_argument("--engine", required=True, help="engine tag, e.g. ds4-v0.5.6")
    ap.add_argument("--engine-config", default="", help="free-form config string")
    ap.add_argument("--workload", default="draftable",
                    help="workload name under bench/workloads/ or a directory path")
    ap.add_argument("--concurrency", type=int, nargs="+", default=[1, 2, 4, 8, 12])
    ap.add_argument("--repeats", type=int, default=1,
                    help="repeats per point; use >=3 for record claims")
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--warmup-seconds", type=int, default=30)
    ap.add_argument("--measure-seconds", type=int, default=180)
    ap.add_argument("--gpu-ssh-host", default="", help="ssh host for nvidia-smi")
    ap.add_argument("--api-key", default=os.environ.get(
        "AGENT_BENCH_API_KEY", os.environ.get("OPENAI_API_KEY", "")))
    ap.add_argument("--outdir", default=str(HERE / "results"))
    args = ap.parse_args()
    if args.gpu_ssh_host.startswith("-"):
        raise SystemExit("error: --gpu-ssh-host must be a hostname, not an option")

    prompts = load_prompts(args.workload)
    base_url = preflight(args.base_url, args.api_key or None)
    workload_tag = Path(args.workload).name
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    try:
        git_hash = subprocess.run(
            ["git", "-C", str(HERE.parent), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True).stdout.strip()
    except Exception:
        git_hash = ""
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    outfile = outdir / f"{stamp}-{args.engine}-{workload_tag}.csv"
    errfile = outdir / f"{stamp}-{args.engine}-{workload_tag}.errors.jsonl"

    meta_fields = ["timestamp_utc", "git_hash", "engine", "engine_config",
                   "workload", "model", "repeat", "max_tokens", "temperature",
                   "top_p"]
    point_fields = ["concurrency", "requests_ok", "requests_err",
                    "first_error_ts", "tokens_in_window", "window_s",
                    "aggregate_tok_s", "decode_tok_s_median",
                    "prefill_tok_s_median", "per_stream_wall_tok_s_median",
                    "ttft_p50_ms", "ttft_p95_ms", "ttft_samples", "itl_p50_ms",
                    "token_source", "skipped_sse_lines", "truncated_streams",
                    "power_w_max", "power_w_mean", "temp_c_max",
                    "mem_used_mib_max", "sm_clock_min", "sm_clock_max",
                    "throttle_seen", "gpu_samples"]
    failed_points = 0
    with open(outfile, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=meta_fields + point_fields)
        w.writeheader()
        for repeat in range(1, args.repeats + 1):
            for c in args.concurrency:
                print(f"=== c={c} repeat={repeat} ({workload_tag}) ===", flush=True)
                t_ann = int(time.time() * 1000)
                point, errors = asyncio.run(run_point(c, args, base_url, prompts))
                grafana_annotate(
                    f"{args.engine} {workload_tag} C{c} r{repeat}: "
                    f"{point['aggregate_tok_s']} tok/s agg",
                    ["bench", args.engine, workload_tag, f"c{c}"],
                    t_ann, int(time.time() * 1000))
                if errors:
                    with open(errfile, "a") as ef:
                        for e in errors:
                            ef.write(json.dumps(e) + "\n")
                if point["requests_ok"] == 0:
                    failed_points += 1
                    print(f"POINT FAILED: c={c} repeat={repeat} — see {errfile}",
                          file=sys.stderr, flush=True)
                point.update({
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "git_hash": git_hash, "engine": args.engine,
                    "engine_config": args.engine_config, "workload": workload_tag,
                    "model": args.model, "repeat": repeat,
                    "max_tokens": args.max_tokens,
                    "temperature": args.temperature, "top_p": args.top_p,
                })
                w.writerow(point)
                f.flush()
                print(json.dumps(point, indent=2), flush=True)
    print(f"\nresults -> {outfile}")
    if failed_points:
        raise SystemExit(f"error: {failed_points} point(s) had zero successful requests")


if __name__ == "__main__":
    main()
