"""LIVE acceptance for B-4 (config-driven metrics) against a running compose.sharded.yaml project.

Disposable project only (it stops and restarts the writer and edits app/config/metrics.json, then restores it):
  AX_API_PORT=18291 AX_SHARD_A_PORT=25771 AX_SHARD_B_PORT=25772 AX_SEED_ORDERS=4000 \
    docker compose -p ax-b4test -f compose.sharded.yaml up -d --build --wait
  python3 -I app/tests/live_b4_check.py ax-b4test 18291 25771 25772
Run from hackathon/. Every check is an assertion; exit 0 only if all pass.

The oracle is independent of the API code. It recomputes numerator and denominator per group key straight from raw
ax.orders on the tenant's OWNING shard, as quantity * unit_price_cents (not the trigger-maintained line_cents), and
rounds in PostgreSQL. The API reads the stream tables plus raw edges.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path

PROJECT, API_PORT, PA, PB = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
B = f"http://127.0.0.1:{API_PORT}"
SU = os.environ.get("AX_DB_SUPERUSER_PASSWORD", "local-demo-superuser")
COMPOSE = ["docker", "compose", "-p", PROJECT, "-f", "compose.sharded.yaml"]
CONFIG = Path("app/config/metrics.json")
STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
OUT = Path(f"app/tests/results/live-b4-{STAMP}")
SHARD_PORT = {"a": PA, "b": PB}
DIRECTORY = json.loads(Path("sharding/directory.v1.json").read_text())["tenants"]
results = []


def check(name, ok, **detail):
    results.append({"check": name, "pass": bool(ok), **detail})
    print(("PASS " if ok else "FAIL ") + name + (f"  {json.dumps(detail, default=str)[:300]}" if detail else ""),
          flush=True)
    return ok


def session(email=None):
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    if email:
        op.open(urllib.request.Request(B + "/api/auth/login",
                                       json.dumps({"email": email, "password": "demo1234"}).encode(),
                                       {"content-type": "application/json"}), timeout=10).read()
    return op


def get(op, path):
    try:
        with op.open(B + path, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def psql(port, sql):
    out = subprocess.run(["psql", "-h", "127.0.0.1", "-p", str(port), "-U", "postgres", "-d", "aggregatex", "-XAtq",
                          "-F", "\t", "-v", "ON_ERROR_STOP=1", "-c", sql], capture_output=True, text=True,
                         env={"PGPASSWORD": SU, "PATH": "/usr/bin:/bin:/opt/homebrew/bin:/usr/local/bin"})
    if out.returncode:
        raise RuntimeError(out.stderr.strip())
    return out.stdout.strip()


def save(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(obj if isinstance(obj, str) else json.dumps(obj, indent=2, default=str))


# ── independent oracle ───────────────────────────────────────────────────────
MEASURE = {"orders": "1", "units": "o.quantity", "gross_cents": "o.quantity::bigint * o.unit_price_cents"}
STATUS_SETS = {"all": None, "sale": ("pending", "paid", "shipped"), "not_sale": ("cancelled", "refunded")}
KEY = {"total": "'total'", "status": "o.status", "product": "o.product_id::text", "category": "p.category_id::text",
       "day": "to_char(date_trunc('day', o.created_at AT TIME ZONE 'UTC'), 'YYYY-MM-DD\"T\"HH24:MI:SS\"+00:00\"')",
       "hour": "to_char(date_trunc('hour', o.created_at AT TIME ZONE 'UTC'), 'YYYY-MM-DD\"T\"HH24:MI:SS\"+00:00\"')"}


def _part(part):
    st = part["resolved_statuses"]
    cond = "true" if len(st) == 5 else "o.status IN (" + ",".join(f"'{s}'" for s in st) + ")"
    return f"COALESCE(sum({MEASURE[part['measure']]}) FILTER (WHERE {cond}), 0)"


def oracle(metric, tenant, f, t, group_by):
    num = _part(metric["numerator"])
    den = _part(metric["denominator"]) if metric["denominator"] else "NULL"
    val = num if metric["type"] == "sum" else \
        f"round(({num})::numeric * {metric['scale']} / NULLIF({den}, 0), {metric['decimals']})"
    join = "JOIN ax.products p ON p.tenant_id = o.tenant_id AND p.product_id = o.product_id" \
        if group_by == "category" else ""
    sql = f"""SELECT {KEY[group_by]}, {num}, {den}, {val} FROM ax.orders o {join}
              WHERE o.tenant_id = {int(tenant)} AND o.created_at >= '{f}' AND o.created_at < '{t}' GROUP BY 1"""
    out = {}
    for line in psql(SHARD_PORT[DIRECTORY[str(tenant)]], sql).splitlines():
        k, n, d, v = line.split("\t")
        out[k] = (int(n), int(d) if d else None, None if v == "" else float(v))
    return out


def fingerprint(port):
    return psql(port, """SELECT (SELECT count(*) FROM ax.orders) || ' ' ||
        (SELECT md5(string_agg(order_id || ':' || status || ':' || quantity || ':' || unit_price_cents || ':' ||
                               created_at, ',' ORDER BY order_id)) FROM ax.orders) || ' ' ||
        (SELECT md5(string_agg(product_id || ':' || category_id || ':' || name, ',' ORDER BY tenant_id, product_id))
           FROM ax.products)""")


def st_oracle(port):
    return psql(port, "SELECT string_agg(stream_table || '=' || missing_in_st || '/' || extra_in_st, ' ' "
                      "ORDER BY stream_table) FROM ax.oracle_mismatches()")


def wait_clean(timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        states = {s: st_oracle(p) for s, p in SHARD_PORT.items()}
        if all(v.count("=0/0") == 3 for v in states.values()):
            return states
        time.sleep(2)
    return states


def compare(api_body, expect):
    """API rows/total vs oracle {key: (num, den, value)}. Returns a list of differences."""
    diffs = []
    rows = {str(r["key"]): (r["numerator"], r["denominator"], r["value"]) for r in api_body["rows"]}
    for k, got in rows.items():
        want = expect.get(k)
        if want is None or got[0] != want[0] or got[1] != want[1] or \
                (got[2] is None) != (want[2] is None) or (got[2] is not None and abs(got[2] - want[2]) > 1e-9):
            diffs.append({"key": k, "api": got, "oracle": want})
    if api_body["row_count"] != len(expect):
        diffs.append({"row_count": api_body["row_count"], "oracle_keys": len(expect)})
    if not api_body["truncated"] and len(rows) != len(expect):
        diffs.append({"missing_keys": sorted(set(expect) - set(rows))[:5]})
    return diffs


def check_total(api_body, metric, tenant, f, t):
    want = oracle(metric, tenant, f, t, "total").get("total", (0, 0 if metric["denominator"] else None, None))
    if metric["type"] == "sum" and want[2] is None:
        want = (want[0], None, want[0])
    got = api_body["total"]
    return (got["numerator"], got["denominator"]) == want[:2] and \
        ((got["value"] is None and want[2] is None) or abs((got["value"] or 0) - (want[2] or 0)) < 1e-9), got, want


WINDOWS = [("2026-08-15T07:30:00+00:00", "2026-09-20T13:45:00+00:00"),   # 36 d, partial edges both ends
           ("2026-10-01T00:00:00+00:00", "2026-10-08T00:00:00+00:00"),   # aligned week (stream tables only)
           ("2026-09-03T22:15:00+00:00", "2026-09-04T03:05:00+00:00")]   # 5 h across midnight (raw only)
TENANTS = [1, 3, 2, 7]                                                     # 1, 3 on shard A; 2, 7 on shard B
SHIPPED = CONFIG.read_bytes()


def matrix(admin, metrics, label):
    n = 0
    for m in metrics:
        for tenant in TENANTS:
            for f, t in WINDOWS:
                long = (datetime.fromisoformat(t) - datetime.fromisoformat(f)).days > 31
                for g in m["group_by"]:
                    if g == "hour" and long:
                        continue
                    q = urllib.parse.urlencode({"from": f, "to": t, "group_by": g, "limit": 50})
                    st, body = get(admin, f"/api/tenants/{tenant}/metrics/{m['id']}?{q}")
                    if st != 200:
                        check(f"{label}: {m['id']} t{tenant} {g} HTTP 200", False, status=st, body=body)
                        continue
                    diffs = compare(body, oracle(m, tenant, f, t, g))
                    ok_total, got, want = check_total(body, m, tenant, f, t)
                    ok_shard = body["shard"] == DIRECTORY[str(tenant)] and body["tenant_id"] == tenant
                    n += 1
                    if diffs or not ok_total or not ok_shard:
                        check(f"{label}: {m['id']} t{tenant} {g} [{f}, {t})", False, diffs=diffs[:3],
                              total=[got, want], shard=body["shard"])
    return n


def main():
    writer_was = subprocess.run(COMPOSE + ["ps", "--status", "running", "-q", "writer"],
                                capture_output=True, text=True).stdout.strip()
    subprocess.run(COMPOSE + ["stop", "writer"], check=True, capture_output=True)
    try:
        run()
    finally:
        CONFIG.write_bytes(SHIPPED)
        if writer_was:
            subprocess.run(COMPOSE + ["start", "writer"], check=True, capture_output=True)
    passed = sum(r["pass"] for r in results)
    save("results.json", {"project": PROJECT, "stamp": STAMP, "passed": passed, "total": len(results),
                          "results": results})
    print(f"\n{passed}/{len(results)} checks passed · evidence: {OUT}")
    sys.exit(0 if passed == len(results) else 1)


def run():
    states = wait_clean()
    check("precondition: writer stopped, stream tables exact on both shards (oracle 0/0 x3)",
          all(v.count("=0/0") == 3 for v in states.values()), **states)
    before = {s: fingerprint(p) for s, p in SHARD_PORT.items()}
    admin, t1, t2, anon = session("admin@demo.local"), session("tenant1@demo.local"), session("tenant2@demo.local"), \
        session()

    st, reg = get(t2, "/api/metrics")
    check("GET /api/metrics lists the shipped config (v1, 3 metrics, derived only)",
          st == 200 and reg["registry_version"] == 1 and len(reg["metrics"]) == 3
          and reg["kind"] == "derived_from_existing_stream_tables", status=st, ids=[m["id"] for m in reg["metrics"]])
    save("01-registry-v1.json", reg)

    n = matrix(admin, reg["metrics"], "oracle v1")
    check(f"oracle v1: every metric x tenant (A: 1,3; B: 2,7) x window x grouping equals raw ax.orders "
          f"({n} responses)", n > 0 and all(r["pass"] for r in results), responses=n)

    # ── security and errors ──
    q = "?from=2026-10-01T00:00:00Z&to=2026-10-08T00:00:00Z"
    st, _ = get(t2, f"/api/tenants/1/metrics/average_order_value{q}")
    check("tenant 2 reading tenant 1 metric -> 403", st == 403, status=st)
    st, body = get(t2, f"/api/tenants/2/metrics/average_order_value{q}")
    check("tenant 2 own metric -> 200 on shard b", st == 200 and body["shard"] == "b", status=st)
    st, body = get(t1, f"/api/tenants/1/metrics/average_order_value{q}")
    check("tenant 1 own metric -> 200 on shard a", st == 200 and body["shard"] == "a", status=st)
    st, _ = get(anon, f"/api/tenants/2/metrics/average_order_value{q}")
    check("no session -> 401", st == 401, status=st)
    st, _ = get(anon, "/api/metrics")
    check("no session listing -> 401", st == 401, status=st)
    for path, want, why in [("/api/tenants/2/metrics/pending_share_pct", 404, "metric not yet in config"),
                            ("/api/tenants/2/metrics/x%3B%20DROP%20TABLE%20ax.orders", 404, "injection-shaped id"),
                            ("/api/tenants/2/metrics/average_order_value?group_by=hour", 422, "grouping not allowed"),
                            ("/api/tenants/2/metrics/units_sold?group_by=customer", 422, "unsupported rollup"),
                            ("/api/tenants/2/metrics/units_sold?group_by=status%3Bselect", 422, "injection grouping"),
                            ("/api/tenants/2/metrics/units_sold?from=2025-01-01T00:00:00Z&to=2026-10-01T00:00:00Z",
                             422, "range > 400 d"),
                            ("/api/tenants/2/metrics/cancel_rate_pct?group_by=hour&from=2026-08-01T00:00:00Z"
                             "&to=2026-10-01T00:00:00Z", 422, "hourly > 31 d")]:
        st, body = get(t2, path)
        check(f"{why} -> {want}", st == want, status=st, detail=(body or {}).get("detail"))

    # ── B-4 acceptance: add a metric by editing ONLY the config file ──
    st, before_resp = get(t2, f"/api/tenants/2/metrics/pending_share_pct{q}")
    save("02-before-new-metric.json", {"status": st, "body": before_resp})
    doc = json.loads(SHIPPED)
    doc["version"] = 2
    doc["metrics"].append({"id": "pending_share_pct", "label": "Pending order share",
                           "description": "Pending orders as a percentage of all orders.",
                           "type": "ratio", "unit": "percent",
                           "numerator": {"measure": "orders", "statuses": ["pending"]},
                           "denominator": {"measure": "orders", "statuses": "all"},
                           "scale": 100, "decimals": 2, "group_by": ["total", "day", "category"]})
    new_text = json.dumps(doc, indent=2) + "\n"
    save("config-v1.json", SHIPPED.decode())
    save("config-v2.json", new_text)
    t0 = time.monotonic()
    tmp = CONFIG.with_suffix(".tmp")
    tmp.write_text(new_text)
    os.replace(tmp, CONFIG)                          # like an editor save: new inode
    reg2 = None
    while time.monotonic() - t0 < 10:
        st, reg2 = get(t2, "/api/metrics")
        if st == 200 and reg2["registry_version"] == 2:
            break
        time.sleep(0.2)
    took = round(time.monotonic() - t0, 2)
    check("config edit -> new metric listed without restart or code change",
          reg2 and reg2.get("registry_version") == 2 and "pending_share_pct" in [m["id"] for m in reg2["metrics"]],
          seconds=took)
    save("03-registry-v2.json", reg2)
    st, after_resp = get(t2, f"/api/tenants/2/metrics/pending_share_pct{q}")
    save("04-after-new-metric.json", {"status": st, "body": after_resp})
    check("new metric before edit 404, after edit 200", before_resp and st == 200, after=st)
    new = [m for m in reg2["metrics"] if m["id"] == "pending_share_pct"]
    k = len(results)
    n2 = matrix(admin, new, "oracle new metric")
    check(f"oracle: new metric equals raw ax.orders on both shards ({n2} responses)",
          n2 > 0 and all(r["pass"] for r in results[k:]), responses=n2)

    # ── invalid config fails closed, other endpoints unaffected, fix restores ──
    bad = json.loads(new_text)
    bad["version"] = 3
    bad["metrics"].append({**bad["metrics"][-1], "id": "evil", "sql": "SELECT * FROM ax.orders"})
    bad["metrics"].append({**bad["metrics"][-2], "id": "by_customer", "group_by": ["customer"]})
    os.replace(_write(tmp, json.dumps(bad)), CONFIG)
    time.sleep(0.3)
    st, body = get(t2, "/api/metrics")
    errs = (body or {}).get("detail", {}).get("errors", []) if isinstance((body or {}).get("detail"), dict) else []
    save("05-invalid-config-response.json", {"status": st, "body": body})
    check("invalid config -> 503 with each validation error, no metric served", st == 503 and
          any("'sql'" in e for e in errs) and any("customer" in e for e in errs), status=st, errors=errs)
    st, _ = get(t2, f"/api/tenants/2/metrics/average_order_value{q}")
    check("invalid config -> metric query also 503 (fail closed)", st == 503, status=st)
    st, _ = get(t2, f"/api/tenants/2/summary{q}")
    check("invalid config does not affect /summary", st == 200, status=st)
    os.replace(_write(tmp, SHIPPED.decode()), CONFIG)
    time.sleep(0.3)
    st, body = get(t2, "/api/metrics")
    check("restoring the shipped config -> v1 again", st == 200 and body["registry_version"] == 1, status=st)

    # ── regression: existing endpoints still answer; zero data mutation ──
    for path in ("/summary", "/trends", "/top-products", "/breakdown?by=category", "/freshness"):
        st, body = get(t2, f"/api/tenants/2{path}{'&' if '?' in path else '?'}{q[1:]}")
        check(f"regression: {path} 200 with B-1 freshness" if path != "/freshness" else "regression: /freshness 200",
              st == 200 and (path == "/freshness" or body.get("freshness") is not None), status=st)
    st, _ = get(admin, "/api/limits")
    check("regression: B-3 /api/limits 200 (operator)", st == 200, status=st)
    st, _ = get(admin, "/api/monitoring")
    check("regression: monitoring 200 (operator)", st == 200, status=st)
    after = {s: fingerprint(p) for s, p in SHARD_PORT.items()}
    check("zero data mutation: ax.orders + ax.products fingerprints unchanged on both shards", before == after,
          before=before, after=after)
    states = {s: st_oracle(p) for s, p in SHARD_PORT.items()}
    check("stream tables still exact after the run", all(v.count("=0/0") == 3 for v in states.values()), **states)


def _write(p, text):
    p.write_text(text)
    return p


if __name__ == "__main__":
    main()
