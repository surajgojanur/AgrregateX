"""End-to-end HTTP latency of the four analytics endpoints on a scale dataset (issue #42 P1-4, #31).

Read-only: issues GET requests only. Run against a disposable scale stack, e.g.
  python3 -I http_latency.py --api http://127.0.0.1:8095 --dsn "host=127.0.0.1 port=25580 dbname=aggregatex \
      user=postgres password=..." --n 50 --out results/1m-http
Scenarios: endpoint x tenant role (largest / median / smallest by order count) x window
(1 h, 1 d, 7 d, 30 d, 90 d, and an unaligned partial-edge window). Each scenario: --warmup requests
discarded, then --n sequential requests (concurrency 1 = service latency, not throughput).
Latency is client wall time per request (connect + server + transfer), monotonic clock.
"""
import argparse
import json
import os
import statistics
import subprocess
import time
import urllib.error
import urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("--api", required=True)
ap.add_argument("--dsn", required=True, help="libpq DSN of the scale DB (read-only queries: counts, data end)")
ap.add_argument("--n", type=int, default=50)
ap.add_argument("--warmup", type=int, default=3)
ap.add_argument("--out", required=True)
args = ap.parse_args()
os.makedirs(args.out, exist_ok=True)


def sql(q):
    r = subprocess.run(["psql", args.dsn, "-XAtq", "-v", "ON_ERROR_STOP=1", "-c", q], capture_output=True, text=True, check=True)
    return r.stdout.strip()


counts = [tuple(map(int, l.split("|"))) for l in sql(
    "select tenant_id, count(*) from ax.orders group by 1 order by 2 desc, 1").splitlines()]
roles = {"largest": counts[0], "median": counts[len(counts) // 2], "smallest": counts[-1]}
total = sum(c for _, c in counts)
end = sql("select to_char(date_trunc('hour', max(created_at)) + interval '1 hour', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') from ax.orders")


def back(hours):
    return sql(f"select to_char(timestamptz '{end}' - interval '{hours} hours', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"')")


WINDOWS = {"1h": (back(1), end), "1d": (back(24), end), "7d": (back(24 * 7), end),
           "30d": (back(24 * 30), end), "90d": (back(24 * 89), end),
           # unaligned edges: exercises raw partial-bucket scans on both ends
           "partial_7d": (sql(f"select to_char(timestamptz '{end}' - interval '7 days 3 hours 17 minutes', "
                              "'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"')"), back(0.25))}
ENDPOINTS = {"summary": "summary", "trends": "trends", "top_products": "top-products", "breakdown": "breakdown"}


def get(path):
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(args.api + path, timeout=30) as r:
            r.read()
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception:  # noqa: BLE001 - timeouts / connection errors are counted, never dropped
        code = "error"
    return (time.perf_counter() - t0) * 1000, code


def pct(v, q):
    v = sorted(v)
    return round(v[min(len(v) - 1, max(0, int(round(q * len(v))) - 1))], 2) if v else None


rows = []
for role, (tenant, n_orders) in roles.items():
    for wname, (f, t) in WINDOWS.items():
        for ename, ep in ENDPOINTS.items():
            grain = "&grain=hour" if ename == "trends" and wname in ("1h", "1d", "7d", "partial_7d") else \
                    ("&grain=day" if ename == "trends" else "")
            path = f"/api/tenants/{tenant}/{ep}?from={f}&to={t}{grain}"
            for _ in range(args.warmup):
                get(path)
            lat, codes = [], {}
            for _ in range(args.n):
                ms, code = get(path)
                codes[str(code)] = codes.get(str(code), 0) + 1
                if code == 200:
                    lat.append(ms)
            row = {"endpoint": ename, "tenant_role": role, "tenant_id": tenant, "tenant_orders": n_orders,
                   "window": wname, "from": f, "to": t, "n": args.n, "status_counts": codes,
                   "errors": args.n - codes.get("200", 0),
                   "p50": pct(lat, .5), "p95": pct(lat, .95), "p99": pct(lat, .99),
                   "max": round(max(lat), 2) if lat else None, "mean": round(statistics.mean(lat), 2) if lat else None}
            rows.append(row)
            print(json.dumps(row), flush=True)

all_ok = [r for r in rows if r["errors"] == 0]
summary = {
    "api": args.api, "orders_total": total, "tenants": len(counts), "data_end": end, "roles": roles,
    "requests": len(rows) * args.n, "errors": sum(r["errors"] for r in rows),
    "worst_p95_ms": max((r["p95"] for r in all_ok), default=None),
    "worst_p99_ms": max((r["p99"] for r in all_ok), default=None),
    "worst_max_ms": max((r["max"] for r in all_ok), default=None),
    "scenarios_p95_under_200ms": sum(1 for r in all_ok if r["p95"] < 200),
    "scenarios_p95_under_1000ms": sum(1 for r in all_ok if r["p95"] < 1000),
    "scenarios": len(rows),
    "versions": sql("select version() || ' | pg_trickle ' || extversion from pg_extension where extname='pg_trickle'"),
}
json.dump(rows, open(os.path.join(args.out, "scenarios.json"), "w"), indent=1)
json.dump(summary, open(os.path.join(args.out, "summary.json"), "w"), indent=1)
print(json.dumps(summary, indent=1))
