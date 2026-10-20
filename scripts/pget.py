"""Parallel ranged downloader with per-chunk resume (stdlib only). pget.py URL OUT [workers] [chunkMB]"""
import os, sys, json, time, threading, urllib.request
url, out = sys.argv[1], sys.argv[2]
W = int(sys.argv[3]) if len(sys.argv) > 3 else 8
CH = (int(sys.argv[4]) if len(sys.argv) > 4 else 256) * 1048576
state = out + ".pget.json"
def head():
    r = urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60)
    return int(r.headers["Content-Length"])
total = head()
done = set(json.load(open(state))["done"]) if os.path.exists(state) else set()
if not os.path.exists(out) or os.path.getsize(out) != total:
    with open(out, "r+b" if os.path.exists(out) else "wb") as f: f.truncate(total)
chunks = [(i, i * CH, min((i + 1) * CH, total) - 1) for i in range((total + CH - 1) // CH) if i not in done]
lock = threading.Lock(); fails = {}
def save():
    with lock: json.dump({"done": sorted(done)}, open(state, "w"))
def fetch(i, a, b):
    for attempt in range(50):
        try:
            req = urllib.request.Request(url, headers={"Range": "bytes=%d-%d" % (a, b)})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            if len(data) != b - a + 1: raise IOError("short %d" % len(data))
            with open(out, "r+b") as f: f.seek(a); f.write(data)
            with lock: done.add(i)
            save(); return
        except Exception as e:
            fails[i] = str(e)[:80]; time.sleep(min(60, 2 + attempt * 3))
    raise SystemExit("chunk %d failed permanently: %s" % (i, fails.get(i)))
q = list(chunks); t0 = time.time()
def worker():
    while True:
        with lock:
            if not q: return
            c = q.pop(0)
        fetch(*c)
ts = [threading.Thread(target=worker, daemon=True) for _ in range(W)]
[t.start() for t in ts]
last = len(done)
while any(t.is_alive() for t in ts):
    time.sleep(30)
    n = len(done); print("progress %d/%d chunks (%.1f GB) %.1f MB/s" % (n, (total + CH - 1) // CH, n * CH / 1e9, (n - last) * CH / 30 / 1048576), flush=True); last = n
print("DONE %s %d bytes" % (out, total), flush=True)
