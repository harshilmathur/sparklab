#!/usr/bin/env python3
"""Warm-vs-cold prefix TTFT probe.

Sends the SAME long prefix twice with different tail questions:
  request 1 (cold): full prefill of the prefix
  request 2 (warm): prefix should hit the KV prefix cache; only the tail
                    prefills. The wall-time ratio is the 1M-usability story.
Uses a fixed seed per depth so the prefix is byte-identical between the
two requests, and a unique run nonce so repeated script runs stay cold.

Usage:
  python3 bench/warm_prefix_probe.py --base-url http://spark2:8000 \
      --model deepseek-v4-flash-0731-exl3-k2 --engine k2-9b2b1e3 \
      --target-tokens 92000 370000
"""
import argparse, json, random, time, urllib.request, csv, os, datetime

FILLER = (
    "The maintenance crew inspected the turbine housing on schedule. "
    "Ambient readings stayed within the approved band all week. "
    "The supervisor filed the report before the shift change. "
    "No deviation from the standard procedure was recorded that day. "
)

def build_prefix(target_tokens: int, nonce: str) -> str:
    reps = max(1, int(target_tokens * 4.2 / len(FILLER)))
    head = (f"Log archive {nonce}. Read the log below and answer the "
            "question at the end.\n\n")
    return head + FILLER * reps

def ask(base, model, prefix, question, timeout):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prefix + "\n\n" + question}],
        "max_completion_tokens": 32,
        "temperature": 0,
    }).encode()
    req = urllib.request.Request(
        base.rstrip("/") + "/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.load(r)
    wall = time.time() - t0
    u = resp.get("usage", {})
    det = (u.get("prompt_tokens_details") or {})
    return {
        "wall_s": round(wall, 1),
        "prompt_tokens": u.get("prompt_tokens"),
        "cached_tokens": det.get("cached_tokens"),
        "answer": resp["choices"][0]["message"]["content"].strip()[:40],
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--engine", required=True)
    ap.add_argument("--target-tokens", nargs="+", type=int, required=True)
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--outdir", default="bench/results")
    args = ap.parse_args()

    nonce = "N" + str(random.randint(10**8, 10**9))
    rows = []
    for t in args.target_tokens:
        prefix = build_prefix(t, nonce + str(t))
        for phase, q in (("cold", "How many distinct sentences repeat in this log? Answer with a number."),
                         ("warm", "What department filed the reports in this log? Answer briefly.")):
            print(f"=== {t} tokens {phase} ===", flush=True)
            try:
                row = ask(args.base_url, args.model, prefix, q, args.timeout)
            except Exception as e:
                row = {"error": str(e)[:200]}
            row.update({"target_tokens": t, "phase": phase, "engine": args.engine,
                        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()})
            print(json.dumps(row, indent=2), flush=True)
            rows.append(row)

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(args.outdir, f"{stamp}-{args.engine}-warmprefix.csv")
    keys = sorted({k for r in rows for k in r})
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)
    print(f"results -> {path}")

if __name__ == "__main__":
    main()
