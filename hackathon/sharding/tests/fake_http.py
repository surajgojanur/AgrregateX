#!/usr/bin/env python3
"""Fake curl for partition_demo.sh: answers like the AggregateX API, deriving the partition from the
fake docker state (API detached from net_a => shard A tenants 503). BUG_A_200=1 makes tenant 1
answer 200 during the partition (a fail-open bug the script must catch)."""
import json, os, re, sys
a = sys.argv[1:]
out = a[a.index("-o") + 1] if "-o" in a else None
url = [x for x in a if x.startswith("http")][0]
path = re.sub(r"^https?://[^/]+", "", url)
st = json.load(open(os.environ["FAKE_DOCKER_STATE"]))
cut = "aggregatex-sharded_net_a" not in st["containers"]["ax-api"]["networks"]
A = {1, 3, 4}
m = re.match(r"/api/tenants/(\d+)/", path)
t = int(m.group(1)) if m else None
if path == "/api/auth/me":
    code, body = 200, {"user": {"role": "admin"}}
elif t is not None and t in A and cut and not (os.environ.get("BUG_A_200") and t == 1):
    code, body = 503, {"detail": "Shard a is unavailable", "shard": "a", "retryable": True}
elif "/live-write" in path:
    code, body = 200, {"committed": True, "shard": "b", "order_id": 200000001, "lag_ms": 900}
elif path.startswith("/api/shards"):
    code, body = 200, ({"complete": False, "missing_shards": ["a"], "total_orders": None, "partial_total_orders": 5000}
                       if cut else {"complete": True, "missing_shards": [], "total_orders": 10000, "partial_total_orders": None})
elif path.startswith("/api/health"):
    code, body = 200, {"status": "degraded" if cut else "ok"}
else:
    code, body = 200, {"summary": {"orders": 65}}
if out:
    json.dump(body, open(out, "w"))
sys.stdout.write(f"{code} 0.012")
