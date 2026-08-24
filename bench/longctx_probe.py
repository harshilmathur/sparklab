#!/usr/bin/env python3
"""Long-context probe: needle retrieval + timing at increasing prompt depths.

Builds a synthetic haystack of filler prose with one needle (a random
code phrase) buried at ~40% depth, asks the model to retrieve it, and
reports exact prompt tokens (from usage), TTFT-ish wall prefill time,
decode rate, and needle correctness. Token counts are approximate at
build time; the usage field gives the exact number per row.

Usage:
  python3 bench/longctx_probe.py --base-url http://spark2:8000 \
      --model deepseek-v4-flash-0731-exl3-k2 --engine k2-9b2b1e3 \
      --target-tokens 32000 131000 262000 524000 1000000
"""
import argparse, json, random, time, urllib.request, csv, os, datetime

FILLER = (
    "The maintenance crew inspected the turbine housing on schedule. "
    "Ambient readings stayed within the approved band all week. "
    "The supervisor filed the report before the shift change. "
    "No deviation from the standard procedure was recorded that day. "
)  # ~44 tokens per repetition, ~4.2 chars/token


def build_prompt(target_tokens: int, needle: str) -> str:
    reps = max(1, int(target_tokens * 4.2 / len(FILLER)))
    pos = int(reps * 0.4)
    parts = [FILLER] * reps
    parts[pos] = FILLER + f" The secret maintenance code is {needle}. "
    head = (
        "Read the log below. Somewhere inside it there is a sentence naming "
        "a secret maintenance code. At the end, answer with ONLY that code.\n\n"
    )
    return head + "".join(parts) + "\n\nWhat is the secret maintenance code? Answer with only the code."


def probe(base, model, target, timeout):
    needle = "ZX" + str(random.randint(100000, 999999)) + "Q"
    prompt = build_prompt(target, needle)
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
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
    usage = resp.get("usage", {})
    text = resp["choices"][0]["message"]["content"].strip()
    ptok = usage.get("prompt_tokens")
    ctok = usage.get("completion_tokens")
    return {
        "target_tokens": target,
        "prompt_tokens": ptok,
        "completion_tokens": ctok,
        "wall_s": round(wall, 1),
        "prefill_tok_s_approx": round(ptok / wall, 1) if ptok else "",
        "needle_found": needle in text,
        "answer": text[:60],
        "token_source": "usage",
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

    rows = []
    for t in args.target_tokens:
        print(f"=== target {t} tokens ===", flush=True)
        try:
            row = probe(args.base_url, args.model, t, args.timeout)
        except Exception as e:
            row = {"target_tokens": t, "error": str(e)[:200]}
        row["engine"] = args.engine
        row["timestamp_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        print(json.dumps(row, indent=2), flush=True)
        rows.append(row)

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(args.outdir, f"{stamp}-{args.engine}-longctx.csv")
    keys = sorted({k for r in rows for k in r})
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print(f"results -> {path}")


if __name__ == "__main__":
    main()
