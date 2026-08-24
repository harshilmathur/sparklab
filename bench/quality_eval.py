#!/usr/bin/env python3
"""Quality gate for SparkLab (Phase 4). Stdlib only.

Scores a serving endpoint on structurally-checkable tasks — no LLM judge:
  json:    output must parse as JSON and contain required keys/types
  tool:    output must be a JSON array of tool calls with required fields
  exact:   output must contain an exact expected substring
  needle:  a planted fact inside a long filler context must be retrieved

Each scenario runs --repeats times at temp 1.0 (repeats make stochastic
failure rates measurable). Pass-rate per category + overall to CSV.

Usage:
  python3 quality_eval.py --base-url http://spark:8000 --model NAME \
      --engine ds4-v0.5.6 --repeats 3
"""

import argparse
import csv
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def extract_json(text: str):
    """Find the first JSON object/array in text (models wrap in fences/prose)."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1)
    for m in re.finditer(r"[\[{]", text):
        depth = 0
        start = m.start()
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
            elif ch == '"' and not esc:
                in_str = not in_str
            elif not in_str:
                if ch in "[{":
                    depth += 1
                elif ch in "]}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:i + 1])
                        except json.JSONDecodeError:
                            break
    return None


def make_needle(depth_tokens: int, code: str) -> str:
    filler = ("The warehouse inventory system processes shipments daily. "
              "Each pallet is scanned, weighed, and routed to a storage zone. "
              "Temperature logs are archived every hour for compliance. ")
    reps = max(1, depth_tokens * 4 // len(filler))
    third = reps // 3
    return (filler * third
            + f" IMPORTANT: the recovery passphrase for vault seven is '{code}'. "
            + filler * (reps - third))


SCENARIOS = [
    # --- json ---
    {"id": "json-ticket", "cat": "json", "prompt": "Extract to JSON with keys customer(str), product(str), severity(low|medium|high), action_items(list of str). Reply ONLY JSON. Ticket: 'Rita from Volt Cycles: our Chargeline app crashes on login since 2am. Need a fix and a status page update urgently.'",
     "check": lambda o: isinstance(o, dict) and isinstance(o.get("customer"), str) and o.get("severity") in ("low", "medium", "high") and isinstance(o.get("action_items"), list)},
    {"id": "json-invoice", "cat": "json", "prompt": "Reply ONLY with JSON: {\"total_cents\": int, \"currency\": str, \"line_items\": [{\"name\": str, \"cents\": int}]} for: two coffees at $3.50 each and one bagel at $2.25, in USD.",
     "check": lambda o: isinstance(o, dict) and o.get("total_cents") == 925 and len(o.get("line_items", [])) == 2},
    {"id": "json-nested", "cat": "json", "prompt": "Reply ONLY with JSON: an object with key 'servers', a list of 3 objects each having 'host'(str), 'port'(int 1-65535), 'tls'(bool). Invent plausible values.",
     "check": lambda o: isinstance(o, dict) and len(o.get("servers", [])) == 3 and all(isinstance(s.get("port"), int) and 0 < s["port"] < 65536 and isinstance(s.get("tls"), bool) for s in o.get("servers", []))},
    # --- tool ---
    {"id": "tool-plan", "cat": "tool", "prompt": "Tools: read_file(path), write_file(path, content), run_shell(cmd). Task: append the line 'DONE' to /tmp/status.txt. Reply ONLY with a JSON array of tool calls, each {\"tool\": str, \"args\": object}. No prose.",
     "check": lambda o: isinstance(o, list) and len(o) >= 1 and all(isinstance(c, dict) and c.get("tool") in ("read_file", "write_file", "run_shell") and isinstance(c.get("args"), dict) for c in o)},
    {"id": "tool-choice", "cat": "tool", "prompt": "Tools: search_web(query), calculator(expression), get_weather(city). Question: 'what is 17.5% of 2840?' Reply ONLY with a JSON array containing exactly one tool call {\"tool\":..., \"args\":...} — the correct tool.",
     "check": lambda o: isinstance(o, list) and len(o) == 1 and o[0].get("tool") == "calculator"},
    {"id": "tool-multi", "cat": "tool", "prompt": "Tools: book_flight(from_city,to_city,date), book_hotel(city,checkin,nights), notify(message). Task: arrange travel Delhi to Tokyo on 2026-09-10, 3 hotel nights, then notify the user. Reply ONLY a JSON array of the 3 calls in order.",
     "check": lambda o: isinstance(o, list) and len(o) == 3 and [c.get("tool") for c in o] == ["book_flight", "book_hotel", "notify"]},
    # --- exact ---
    {"id": "exact-arith", "cat": "exact", "prompt": "Compute 847 * 63. Reply with the number only.", "expect": "53361"},
    {"id": "exact-sort", "cat": "exact", "prompt": "Sort descending and reply with only the comma-separated list: 14, 3, 91, 27, 8", "expect": "91, 27, 14, 8, 3", "alt": "91,27,14,8,3"},
    {"id": "exact-capital", "cat": "exact", "prompt": "Capital of Australia, one word only.", "expect": "Canberra"},
    {"id": "exact-datemath", "cat": "exact", "prompt": "What date is 45 days after 2026-08-01? Reply YYYY-MM-DD only.", "expect": "2026-09-15"},
    {"id": "exact-hex", "cat": "exact", "prompt": "Convert 255 to hexadecimal. Reply with just the hex digits (no 0x).", "expect": "FF", "alt": "ff"},
    {"id": "exact-regex", "cat": "exact", "prompt": "Which of these matches the regex ^a+b$ : 'aab', 'abb', 'ba'? Reply with the matching string only.", "expect": "aab"},
]


def build_needles():
    out = []
    for depth in (4000, 16000):
        code = f"K{depth}X-{depth * 7 % 9973}"
        out.append({"id": f"needle-{depth}", "cat": "needle",
                    "prompt": make_needle(depth, code)
                    + "\n\nWhat is the recovery passphrase for vault seven? Reply with the passphrase only.",
                    "expect": code})
    return out


EXTRA_BODY = {}

def ask(base_url, model, prompt, max_tokens, api_key):
    payload = {"model": model,
               "messages": [{"role": "user", "content": prompt}],
               "max_tokens": max_tokens, "temperature": 1.0,
               "top_p": 0.95, "stream": False}
    payload.update(EXTRA_BODY)
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(base_url + "/chat/completions", data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=900) as r:
        resp = json.load(r)
    msg = resp["choices"][0]["message"]
    return (msg.get("content") or "") if isinstance(msg, dict) else ""


def score(sc, text) -> bool:
    text_clean = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    if "check" in sc:
        return bool(sc["check"](extract_json(text)))
    if sc["cat"] in ("exact", "needle"):
        if sc["expect"].lower() in text_clean.lower():
            return True
        return bool(sc.get("alt") and sc["alt"].lower() in text_clean.lower())
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--engine", required=True)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--max-tokens", type=int, default=2048)
    ap.add_argument("--api-key", default="")
    ap.add_argument("--outdir", default=str(HERE / "results"))
    ap.add_argument("--extra-body", dest="extra_body", default=None, help="JSON merged into each request body")
    args = ap.parse_args()
    if getattr(args, "extra_body", None):
        EXTRA_BODY.update(json.loads(args.extra_body))
    base = args.base_url.rstrip("/")
    if not base.endswith("/v1"):
        base += "/v1"
    scenarios = SCENARIOS + build_needles()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    outfile = Path(args.outdir) / f"{stamp}-{args.engine}-quality.csv"
    rows = []
    for sc in scenarios:
        passes = 0
        fail_sample = ""
        for r in range(args.repeats):
            try:
                text = ask(base, args.model, sc["prompt"], args.max_tokens, args.api_key)
                if score(sc, text):
                    passes += 1
                elif not fail_sample:
                    fail_sample = text[-160:].replace("\n", " ")
            except Exception as e:
                fail_sample = f"ERROR {e}"[:160]
        rows.append({"scenario": sc["id"], "category": sc["cat"],
                     "passes": passes, "repeats": args.repeats,
                     "pass_rate": round(passes / args.repeats, 3),
                     "fail_sample": fail_sample})
        print(f"{sc['id']:>16}: {passes}/{args.repeats}", flush=True)
    with open(outfile, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["scenario", "category", "passes",
                                          "repeats", "pass_rate", "fail_sample"])
        w.writeheader()
        w.writerows(rows)
    cats = {}
    for r in rows:
        cats.setdefault(r["category"], []).append(r["pass_rate"])
    print(f"\nengine={args.engine}")
    for c, v in cats.items():
        print(f"  {c:>7}: {sum(v)/len(v):.0%} ({len(v)} scenarios)")
    total = sum(r["passes"] for r in rows) / sum(r["repeats"] for r in rows)
    print(f"  OVERALL: {total:.0%}\nresults -> {outfile}")


if __name__ == "__main__":
    main()
