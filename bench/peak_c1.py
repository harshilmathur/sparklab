#!/usr/bin/env python3
"""Peak C1 decode-rate probe, matching MiaAI's headline methodology:
thinking=false, ignore_eos, forced token count, decode rate AFTER first token
(TTFT excluded). Warms the server, then sweeps content x length to find the
ceiling. Reports median decode tok/s across N measured runs per cell."""
import json, time, urllib.request, statistics, itertools, sys

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8888"
MODEL = sys.argv[2] if len(sys.argv) > 2 else "deepseek-v4-flash-dspark"

# content that drafts well (code/repetitive) vs generic prose vs a short chat
PROMPTS = {
  "code": "Write a complete Python implementation of a balanced binary search tree with insert, delete, search, and in-order traversal. Include docstrings.",
  "list": "List the integers from 1 to 200, one per line, as 'N: <english word for N>'.",
  "generic": "Explain how HTTP request routing works in a web framework, step by step.",
}

def decode_run(prompt, n_tokens):
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True, "stream_options": {"include_usage": True},
        "temperature": 0.6, "top_p": 0.95,
        "max_tokens": n_tokens, "min_tokens": n_tokens, "ignore_eos": True,
        "chat_template_kwargs": {"thinking": False},
    }
    req = urllib.request.Request(BASE + "/v1/chat/completions",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    started = time.time(); first = None; out = 0; usage = None
    with urllib.request.urlopen(req, timeout=300) as r:
        for raw in r:
            line = raw.decode().strip()
            if not line.startswith("data: "): continue
            data = line[6:]
            if data == "[DONE]": break
            obj = json.loads(data)
            if obj.get("usage"): usage = obj["usage"]
            ch = obj.get("choices") or []
            if ch and ch[0].get("delta", {}).get("content"):
                if first is None: first = time.time()
                out += 1
    finished = time.time()
    toks = (usage or {}).get("completion_tokens", out)
    decode_s = finished - (first or finished)
    return toks / decode_s if decode_s > 0 else 0

def main():
    print(f"warming ({BASE})...", flush=True)
    for _ in range(6): decode_run(PROMPTS["code"], 128)
    lengths = [128, 256, 512]
    best = (0, None)
    print(f"{'content':8} {'ntok':>5} {'decode tok/s (median of 5)':>28}")
    for name, ntok in itertools.product(PROMPTS, lengths):
        runs = sorted(decode_run(PROMPTS[name], ntok) for _ in range(5))
        med = runs[len(runs)//2]
        print(f"{name:8} {ntok:5d}   {med:6.1f}   (range {runs[0]:.1f}-{runs[-1]:.1f})", flush=True)
        if med > best[0]: best = (med, f"{name}/{ntok}tok")
    print(f"\nPEAK C1 decode: {best[0]:.1f} tok/s  [{best[1]}]  (Mia methodology: thinking off, ignore_eos, decode-only)")

if __name__ == "__main__":
    main()
