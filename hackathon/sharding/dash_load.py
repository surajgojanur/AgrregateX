"""Continuous dashboard load on shard A tenants for N seconds (4 threads). usage: dash_load.py seconds"""
import json, os, sys, threading, time, urllib.error, urllib.request
from http.cookiejar import CookieJar
B = "http://127.0.0.1:8091"; END = time.time() + float(sys.argv[1]); n = [0]
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
try:  # login is on by default; harmless when disabled
    op.open(urllib.request.Request(B + "/api/auth/login", json.dumps({"email": "admin@demo.local",
            "password": os.environ.get("AX_DEMO_PASSWORD", "demo1234")}).encode(), {"content-type": "application/json"}), timeout=10)
except urllib.error.HTTPError:
    pass
PATHS = [f"/api/tenants/{t}/{e}?from=2026-08-01T00:00:00Z" for t in (1, 3, 4) for e in ("summary", "trends", "top-products", "breakdown")]
def run(i):
    k = i
    while time.time() < END:
        op.open(B + PATHS[k % len(PATHS)], timeout=30).read(); k += 1; n[0] += 1
ts = [threading.Thread(target=run, args=(i,)) for i in range(4)]; [t.start() for t in ts]; [t.join() for t in ts]
print(f"dashboard requests: {n[0]} ({n[0]/float(sys.argv[1]):.0f}/s)")
