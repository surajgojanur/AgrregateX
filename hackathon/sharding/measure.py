"""P3 measurements on the sharded demo: HTTP latency per shard/endpoint and commit->visible lag.
usage: python3 -I sharding/measure.py [n_requests] [n_lag]  -> JSON (n=1 laptop run, indicative only)"""
import json, statistics, sys, time, urllib.request
from http.cookiejar import CookieJar
B = "http://127.0.0.1:8091"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 100
NL = int(sys.argv[2]) if len(sys.argv) > 2 else 10
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
try:
    op.open(urllib.request.Request(B + "/api/auth/login", json.dumps({"email": "admin@demo.local", "password": "demo1234"}).encode(),
                                   {"content-type": "application/json"}), timeout=10).read()
except Exception:
    pass  # login disabled
def get(p):
    t = time.monotonic(); r = op.open(B + p, timeout=30); r.read(); return (time.monotonic() - t) * 1000, r.status
def pct(v, q): v = sorted(v); return round(v[min(len(v) - 1, int(q * len(v)))], 1)
out = {"latency_ms": {}, "lag_ms": {}}
for tenant, shard in ((1, "a"), (2, "b")):
    for ep in ("summary", "trends", "top-products", "breakdown?by=category"):
        path = f"/api/tenants/{tenant}/{ep}" + ("&" if "?" in ep else "?") + "from=2026-08-01T00:00:00Z"
        get(path)  # warm-up
        lat = [get(path)[0] for _ in range(N)]
        out["latency_ms"][f"t{tenant}/{shard}/{ep.split('?')[0]}"] = {"n": N, "p50": pct(lat, .5), "p95": pct(lat, .95), "max": round(max(lat), 1)}
    lags = []
    for _ in range(NL):
        req = urllib.request.Request(B + f"/api/tenants/{tenant}/live-write", json.dumps({"action": "insert"}).encode(), {"content-type": "application/json"})
        body = json.loads(op.open(req, timeout=60).read())
        if body.get("lag_ms") is not None:
            lags.append(body["lag_ms"])
        time.sleep(0.3)
    out["lag_ms"][f"t{tenant}/{shard}"] = {"n": len(lags), "of": NL, "p50": pct(lags, .5) if lags else None,
                                          "max": max(lags) if lags else None}
print(json.dumps(out, indent=1))
