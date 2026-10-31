"""LIVE acceptance for B-1, B-2 and B-3 against a running compose.sharded.yaml project.

Run it ONLY against a disposable project (B-2 reinitializes every stream table), e.g.:
  AX_API_PORT=18191 AX_SHARD_A_PORT=25671 AX_SHARD_B_PORT=25672 AX_TENANT_MAX_CONCURRENT=1 AX_TENANT_QUEUE_WAIT_S=0 \
    docker compose -p ax-b2test -f compose.sharded.yaml up -d --build --wait
  python3 -I app/tests/live_bonus_check.py ax-b2test 18191 25671 25672
Every check is an assertion; exit 0 only if all pass. Restores the writer's original state.
"""
import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

PROJECT, API_PORT, PA, PB = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
B = f"http://127.0.0.1:{API_PORT}"
SU = "local-demo-superuser"
COMPOSE = ["docker", "compose", "-p", PROJECT, "-f", "compose.sharded.yaml"]
results = []


def check(name, ok, **detail):
    results.append({"check": name, "pass": bool(ok), **detail})
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail else ""), flush=True)


def session(email):
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    op.open(urllib.request.Request(B + "/api/auth/login", json.dumps({"email": email, "password": "demo1234"}).encode(),
                                   {"content-type": "application/json"}), timeout=10).read()
    return op


def get(op, path):
    try:
        with op.open(B + path, timeout=30) as r:
            return r.status, json.loads(r.read()), {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null"), {k.lower(): v for k, v in e.headers.items()}


def psql(port, sql):
    out = subprocess.run(["psql", "-h", "127.0.0.1", "-p", str(port), "-U", "postgres", "-d", "aggregatex", "-XAtq",
                          "-v", "ON_ERROR_STOP=1", "-c", sql], capture_output=True, text=True,
                         env={"PGPASSWORD": SU, "PATH": "/usr/bin:/bin:/opt/homebrew/bin:/usr/local/bin"})
    if out.returncode:
        raise RuntimeError(out.stderr.strip())
    return out.stdout.strip()


def oracle(port):
    rows = [r.split("|") for r in psql(port, "select stream_table, missing_in_st, extra_in_st from ax.oracle_mismatches()").splitlines()]
    return sorted((n, int(m), int(e)) for n, m, e in rows)


def oracle_clean(rows):
    return [n for n, _, _ in rows] == ["st_day_category_status", "st_day_product_status", "st_hour_category_status"] \
        and all(m == 0 and e == 0 for _, m, e in rows)


writer = f"{PROJECT}-writer-1"
writer_was_running = subprocess.run(["docker", "inspect", writer, "-f", "{{.State.Running}}"],
                                    capture_output=True, text=True).stdout.strip() == "true"
try:
    admin = session("admin@demo.local")
    t2 = session("tenant2@demo.local")

    # ── B-1 ──
    for who, op, tenant in (("operator", admin, 1), ("tenant2", t2, 2)):
        st, body, _ = get(op, f"/api/tenants/{tenant}/summary")
        f = (body or {}).get("freshness") or {}
        check(f"B-1 {who}: summary carries freshness", st == 200 and f.get("verified_at") and f.get("healthy") is True
              and f.get("age_s") is not None and f["age_s"] < 10, http=st, freshness=f)
    for ep in ("trends", "top-products", "breakdown"):
        st, body, _ = get(admin, f"/api/tenants/2/{ep}")
        check(f"B-1 {ep} carries freshness", st == 200 and (body.get("freshness") or {}).get("verified_at"), http=st)

    # ── B-3 (stack started with AX_TENANT_MAX_CONCURRENT=1, AX_TENANT_QUEUE_WAIT_S=0) ──
    codes, headers, other = [], [], []
    rng = "?from=2026-08-01T00:00:00Z"   # 90-day range: a heavier query widens the overlap window

    def flood():
        st, _, h = get(admin, f"/api/tenants/1/summary{rng}")
        codes.append(st)
        headers.append(h.get("retry-after"))

    def tenant2():   # one request at a time: within tenant 2's own limit, so it must never see 429
        for _ in range(3):
            other.append(get(t2, f"/api/tenants/2/summary{rng}")[0])
    threads = [threading.Thread(target=flood) for _ in range(16)] + [threading.Thread(target=tenant2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    n429, n200 = codes.count(429), codes.count(200)
    check("B-3 flood on tenant 1 gets 429s and some 200s", n429 >= 1 and n200 >= 1 and set(codes) <= {200, 429},
          ok_200=n200, rejected_429=n429)
    check("B-3 429 carries Retry-After: 1", all(h == "1" for c, h in zip(codes, headers) if c == 429))
    check("B-3 tenant 2 unaffected by tenant 1's flood (its own slot)", other == [200, 200, 200], tenant2=other)
    st, lim, _ = get(admin, "/api/limits")
    row = next((x for x in lim.get("tenants", []) if x["tenant_id"] == 1), {})
    check("B-3 /api/limits counts the rejections", st == 200 and row.get("rejected_429", 0) >= n429 and row.get("in_flight") == 0,
          limits=row)
    st, _, _ = get(t2, "/api/limits")
    check("B-3 /api/limits is operator-only", st == 403, http=st)

    # ── B-2 ──
    subprocess.run(["docker", "stop", writer], capture_output=True)
    for _ in range(30):
        before = {"a": oracle(PA), "b": oracle(PB)}
        if all(oracle_clean(v) for v in before.values()):
            break
        time.sleep(2)
    check("B-2 pre-check (writes quiesced): oracle clean on both shards", all(oracle_clean(v) for v in before.values()), before=before)
    subprocess.run(["docker", "start", writer], capture_output=True)   # rebuild runs WITH live writes
    t0 = psql(PA, "select now()")
    bad = subprocess.run(COMPOSE + ["exec", "-T", "-e", "AX_DB_SUPERUSER_PASSWORD=wrong-password", "api",
                                    "python", "-m", "axapi.rebuild", "--shard", "a", "--timeout", "20"],
                         capture_output=True, text=True)
    check("B-2 wrong owner password fails closed (exit 1, ok=false)", bad.returncode == 1 and '"ok": false' in bad.stdout,
          exit=bad.returncode)
    t_start = time.monotonic()
    run = subprocess.run(COMPOSE + ["exec", "-T", "-e", f"AX_DB_SUPERUSER_PASSWORD={SU}", "api",
                                    "python", "-m", "axapi.rebuild", "--shard", "all", "--timeout", "120"],
                         capture_output=True, text=True)
    secs = round(time.monotonic() - t_start, 1)
    try:
        rep = json.loads(run.stdout)
    except ValueError:
        rep = {"raw": run.stdout[-500:], "stderr": run.stderr[-500:]}
    check("B-2 rebuild CLI exit 0 and ok=true", run.returncode == 0 and rep.get("ok") is True, exit=run.returncode, seconds=secs,
          shards=[{k: s.get(k) for k in ("shard", "ok", "rebuilt", "oracle_clean", "seconds", "problems")} for s in rep.get("shards", [])])
    for port, sh in ((PA, "a"), (PB, "b")):
        acts = psql(port, f"""select string_agg(s.pgt_name || ':' || h.action || ':' || h.status, ' ' order by s.pgt_name)
                               from pgtrickle.pgt_refresh_history h join pgtrickle.pgt_stream_tables s using (pgt_id)
                              where h.start_time >= '{t0}' and h.action in ('REINITIALIZE','FULL')""")
        check(f"B-2 shard {sh}: pg_trickle history shows a full rebuild of all 3 stream tables",
              all(f"{n}:" in acts for n in ("st_day_product_status", "st_day_category_status", "st_hour_category_status"))
              and "FAILED" not in acts, history=acts)
    # independent post-check with writes quiesced
    subprocess.run(["docker", "stop", writer], capture_output=True)
    after = {}
    for _ in range(30):
        after = {"a": oracle(PA), "b": oracle(PB)}
        if all(oracle_clean(v) for v in after.values()):
            break
        time.sleep(2)
    check("B-2 independent oracle after rebuild: 0/0 on both shards", all(oracle_clean(v) for v in after.values()), after=after)
    st, body, _ = get(admin, "/api/tenants/1/summary")
    check("B-2 API serving after rebuild", st == 200 and (body.get("freshness") or {}).get("healthy") is True, http=st)
finally:
    subprocess.run(["docker", "start" if writer_was_running else "stop", writer], capture_output=True)

failed = [r for r in results if not r["pass"]]
print(json.dumps({"passed": len(results) - len(failed), "failed": len(failed)}))
sys.exit(1 if failed else 0)
