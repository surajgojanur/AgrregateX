#!/usr/bin/env python3
"""Fake psql: shard row counts (A grows only via the demo's local insert), oracle 0, placement checks."""
import json, os, sys
a = sys.argv[1:]; q = a[a.index("-c") + 1] if "-c" in a else ""
port = a[a.index("-p") + 1]
f = os.environ["FAKE_PSQL_STATE"]
st = json.load(open(f)) if os.path.exists(f) else {"25571": 5000, "25572": 5000}
if q.startswith("insert"):
    st[port] += 25; json.dump(st, open(f, "w")); sys.exit(0)
if "oracle_mismatches" in q:
    print("0" if "coalesce" in q else "0/0 0/0 0/0")
elif "order_id=200000001" in q:
    print("1" if port == "25572" and "tenant_id=2" in q else "0")
elif "created_at >=" in q:
    print("65")
elif "count(*) from ax.orders" in q:
    print(st[port])
json.dump(st, open(f, "w"))
