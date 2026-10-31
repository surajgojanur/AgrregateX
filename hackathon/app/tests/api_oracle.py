"""API-vs-SQL oracle: every API answer must equal a direct recomputation from raw ax.orders.

Run with writes paused (docker compose stop writer) after refreshes settle.
usage: python3 -I api_oracle.py [n_windows]   (env: AX_BASE, AX_PG_DSN, AX_DEMO_PASSWORD)
"""
import http.cookiejar
import json
import os
import random
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

import psycopg2

BASE = os.environ.get("AX_BASE", "http://127.0.0.1:8090")
DSN = os.environ.get("AX_PG_DSN", "host=127.0.0.1 port=25560 dbname=aggregatex user=postgres password=local-demo-superuser")
PW = os.environ.get("AX_DEMO_PASSWORD", "demo1234")
UTC = timezone.utc
SALE = "status NOT IN ('cancelled','refunded')"

jar = http.cookiejar.CookieJar()
http_ = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def get(path):
    with http_.open(BASE + path) as r:
        return json.loads(r.read())


req = urllib.request.Request(BASE + "/api/auth/login", data=json.dumps({"email": "admin@demo.local", "password": PW}).encode(),
                             headers={"content-type": "application/json"})
http_.open(req).read()
pg = psycopg2.connect(DSN)
pg.autocommit = True
cur = pg.cursor()


def q(sql, args):
    cur.execute(sql, args)
    return cur.fetchall()


def windows(n):
    rnd = random.Random(7)
    lo = datetime(2026, 8, 2, tzinfo=UTC)
    hi = datetime.now(UTC)
    fixed = [(datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 10, 1, tzinfo=UTC)),          # exact days, no edges
             (datetime(2026, 9, 1, 13, 7, 11, tzinfo=UTC), datetime(2026, 9, 1, 17, 0, tzinfo=UTC)),  # inside one day
             (datetime(2026, 9, 3, 23, 59, 59, tzinfo=UTC), datetime(2026, 9, 4, 0, 0, 1, tzinfo=UTC))]  # 2 s across midnight
    out = fixed[:]
    while len(out) < n:
        a = lo + (hi - lo) * rnd.random()
        b = a + timedelta(seconds=rnd.choice([90, 3600 * 5, 86400 * 2.5, 86400 * 29.3, 86400 * 80]) * rnd.random() + 1)
        out.append((a, min(b, hi)))
    return out


def iso(d):
    return d.isoformat().replace("+00:00", "Z")


fails = 0
checks = 0
for tenant in (1, 2, 7):
    for a, b in windows(int(sys.argv[1]) if len(sys.argv) > 1 else 12):
        rng = f"from={iso(a)}&to={iso(b)}"
        base = f"/api/tenants/{tenant}"
        W = "tenant_id=%s AND created_at >= %s AND created_at < %s"
        # summary
        api = get(f"{base}/summary?{rng}")["summary"]["by_status"]
        sql = {s: {"orders": n, "units": int(u), "gross_cents": int(c)} for s, n, u, c in
               q(f"SELECT status, count(*), sum(quantity), sum(line_cents) FROM ax.orders WHERE {W} GROUP BY 1", (tenant, a, b))}
        checks += 1
        if api != sql:
            fails += 1; print("SUMMARY MISMATCH", tenant, a, b, api, sql)
        # top products (deterministic ties)
        api = [(p["product_id"], p["sales_cents"]) for p in get(f"{base}/top-products?{rng}&limit=10")["products"]]
        sql = [(p, int(c)) for p, c in q(f"SELECT product_id, sum(line_cents) c FROM ax.orders WHERE {W} AND {SALE} "
                                          "GROUP BY 1 ORDER BY c DESC, product_id LIMIT 10", (tenant, a, b))]
        checks += 1
        if api != sql:
            fails += 1; print("TOPN MISMATCH", tenant, a, b, api[:3], sql[:3])
        # category breakdown
        api = {r["key"]: r["sales_cents"] for r in get(f"{base}/breakdown?{rng}&by=category")["rows"]}
        sql = {k: int(c) for k, c in q(f"""SELECT p.category_id, COALESCE(sum(o.line_cents) FILTER (WHERE o.{SALE}),0)
                 FROM ax.orders o JOIN ax.products p USING (tenant_id, product_id)
                WHERE o.tenant_id=%s AND o.created_at >= %s AND o.created_at < %s GROUP BY 1""", (tenant, a, b))}
        checks += 1
        if api != sql:
            fails += 1; print("CATEGORY MISMATCH", tenant, a, b)
        # trends (day always; hour when <= 31 days)
        for grain in (["day", "hour"] if b - a <= timedelta(days=31) else ["day"]):
            api = {p["bucket"]: (p["orders"], p["sales_cents"]) for p in get(f"{base}/trends?{rng}&grain={grain}")["points"]}
            sql = {k.replace(tzinfo=UTC).isoformat(): (n, int(c)) for k, n, c in q(
                f"SELECT date_trunc('{grain}', created_at AT TIME ZONE 'UTC'), count(*), "
                f"COALESCE(sum(line_cents) FILTER (WHERE {SALE}),0) FROM ax.orders WHERE {W} GROUP BY 1", (tenant, a, b))}
            checks += 1
            if api != sql:
                fails += 1; print("TREND MISMATCH", grain, tenant, a, b, len(api), len(sql))

print(json.dumps({"checks": checks, "mismatches": fails}))
sys.exit(1 if fails else 0)
