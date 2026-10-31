"""P3 sharding acceptance checks (run on the host against the compose.sharded.yaml stack).

Checks: directory <-> shard data agreement, tenant disjointness, seed union == AX_SEED_ORDERS,
disjoint order ids, per-shard stream-table oracle (writer must be paused), one real mutation per
shard landing ONLY on its owning shard and visible in that shard's stream tables, and the HTTP
security matrix (needs the API with AX_AUTH_DISABLED=0 for the 401/403 checks).

usage: python3 -I sharding/tests/shard_check.py   -> prints JSON, exit 1 on any failure
"""
from http.cookiejar import CookieJar
import json
import os
import sys
import time
import urllib.error
import urllib.request

import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get("AX_BASE", "http://127.0.0.1:8091")
PW = os.environ.get("AX_DB_SUPERUSER_PASSWORD", "local-demo-superuser")
DEMO_PW = os.environ.get("AX_DEMO_PASSWORD", "demo1234")
SEED = int(os.environ.get("AX_SEED_ORDERS", "10000"))
DSN = {"a": f"host=127.0.0.1 port=25571 dbname=aggregatex user=postgres password={PW}",
       "b": f"host=127.0.0.1 port=25572 dbname=aggregatex user=postgres password={PW}"}
directory = json.load(open(os.path.join(HERE, "..", "directory.v1.json"), encoding="utf-8"))
owner = {int(t): s for t, s in directory["tenants"].items()}

results: list[dict] = []


def check(name, ok, **detail):
    results.append({"check": name, "pass": bool(ok), **detail})


def sql(shard, query, args=()):
    with psycopg2.connect(DSN[shard]) as c, c.cursor() as cur:
        cur.execute(query, args)
        return cur.fetchall()


def http(method, path, body=None, opener=None):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"content-type": "application/json"})
    t0 = time.monotonic()
    try:
        with (opener or urllib.request.build_opener()).open(req, timeout=40) as r:
            return r.status, json.loads(r.read() or b"null"), (time.monotonic() - t0) * 1000
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null"), (time.monotonic() - t0) * 1000


# 1. directory <-> data
tenants = {s: {r[0] for r in sql(s, "SELECT tenant_id FROM ax.tenants")} for s in DSN}
for s in DSN:
    expected = {t for t, o in owner.items() if o == s}
    order_tenants = {r[0] for r in sql(s, "SELECT DISTINCT tenant_id FROM ax.orders")}
    check(f"shard {s}: tenants == directory", tenants[s] == expected and order_tenants <= expected,
          tenants=sorted(tenants[s]), order_tenants=sorted(order_tenants), expected=sorted(expected))
check("no tenant on both shards", not (tenants["a"] & tenants["b"]), overlap=sorted(tenants["a"] & tenants["b"]))

# 2. seed union and disjoint order ids
ids = {s: {r[0] for r in sql(s, "SELECT order_id FROM ax.orders WHERE order_id <= %s", (SEED,))} for s in DSN}
check("seed union == AX_SEED_ORDERS and ids disjoint",
      len(ids["a"]) + len(ids["b"]) == SEED and not (ids["a"] & ids["b"]) and ids["a"] | ids["b"] == set(range(1, SEED + 1)),
      shard_a=len(ids["a"]), shard_b=len(ids["b"]), duplicate_ids=len(ids["a"] & ids["b"]))
for s in DSN:  # all keys / joins tenant-local: every order's product+customer exists in the same tenant on the same shard
    orphans = sql(s, """SELECT count(*) FROM ax.orders o
                         WHERE NOT EXISTS (SELECT 1 FROM ax.products p WHERE p.tenant_id = o.tenant_id AND p.product_id = o.product_id)
                            OR NOT EXISTS (SELECT 1 FROM ax.customers c WHERE c.tenant_id = o.tenant_id AND c.customer_id = o.customer_id)""")[0][0]
    check(f"shard {s}: joins tenant-local (no orphan refs)", orphans == 0, orphans=orphans)

# 3. per-shard stream-table oracle (caller paused the writer and let refreshes settle)
for s in DSN:
    rows = sql(s, "SELECT stream_table, missing_in_st, extra_in_st FROM ax.oracle_mismatches()")
    check(f"shard {s}: stream-table oracle 0/0", all(m == 0 and e == 0 for _, m, e in rows),
          rows=[list(r) for r in rows])

# Operator session for mutations when login is enabled (no-op otherwise).
admin = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
if http("GET", "/api/auth/me")[0] == 401:
    http("POST", "/api/auth/login", {"email": "admin@demo.local", "password": DEMO_PW}, admin)

# 4. one real mutation per shard, visible only on its owner
for tenant in (1, 2):
    s = owner[tenant]
    other = "b" if s == "a" else "a"
    status, body, ms = http("POST", f"/api/tenants/{tenant}/live-write", {"action": "insert"}, admin)
    oid = (body or {}).get("order_id")
    on_owner = sql(s, "SELECT count(*) FROM ax.orders WHERE tenant_id = %s AND order_id = %s", (tenant, oid))[0][0] if oid else 0
    on_other = sql(other, "SELECT count(*) FROM ax.orders WHERE order_id = %s", (oid,))[0][0] if oid else 0
    check(f"tenant {tenant} (shard {s}): live insert lands on owner only and becomes visible",
          status == 200 and body.get("shard") == s and on_owner == 1 and on_other == 0 and body.get("lag_ms") is not None,
          http=status, order_id=oid, lag_ms=(body or {}).get("lag_ms"), visible_after_ms=(body or {}).get("visible_after_ms"))
    status, body, ms = http("POST", f"/api/tenants/{tenant}/live-write", {"action": "cancel", "order_id": oid}, admin)
    check(f"tenant {tenant} (shard {s}): cancel visible", status == 200 and body.get("lag_ms") is not None,
          http=status, lag_ms=(body or {}).get("lag_ms"))

# 5. HTTP security matrix (only meaningful with login enabled)
st, health, _ = http("GET", "/api/health")
auth_on = http("GET", "/api/auth/me")[0] == 401
if auth_on:
    jar = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    http("POST", "/api/auth/login", {"email": "tenant2@demo.local", "password": DEMO_PW}, jar)
    check("tenant 2 (B) reads own summary", http("GET", "/api/tenants/2/summary", opener=jar)[0] == 200)
    check("tenant 2 (B) -> tenant 1 (A) is 403 (auth before routing)", http("GET", "/api/tenants/1/summary", opener=jar)[0] == 403)
    check("tenant 2 (B) -> tenant 3 (A) is 403", http("GET", "/api/tenants/3/summary", opener=jar)[0] == 403)
    check("tenant 2 cannot cancel tenant 1's order", http("POST", "/api/tenants/1/live-write", {"action": "cancel", "order_id": 2}, jar)[0] == 403)
    check("tenant 2 -> /api/shards is 403", http("GET", "/api/shards", opener=jar)[0] == 403)
    check("unauthenticated is 401", http("GET", "/api/tenants/2/summary")[0] == 401)
else:
    results.append({"check": "HTTP security matrix", "pass": None, "status": "NOT RUN (API has AX_AUTH_DISABLED=1)"})

failed = [r for r in results if r["pass"] is False]
print(json.dumps({"health": health.get("status") if isinstance(health, dict) else st, "checks": results,
                  "passed": sum(1 for r in results if r["pass"]), "failed": len(failed)}, indent=1, default=str))
sys.exit(1 if failed else 0)
