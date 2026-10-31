"""G3 database-safety A/B harness (issue #28). Opus-owned; never touches hackathon/benchmark/**.

Arms, all on ONE shard server (same CPU/RAM/disk):
  A  stream tables + normal background writer, NO dashboard load      (db aggregatex)
  B  A + FIXED-RATE real HTTP analytics load through the API            (db aggregatex)
  C  identical schema/data/bucket trigger but NO stream tables / CDC    (db ax_nost)
Per pair the arm order is randomised (seed recorded). Each arm = one pgbench run; the first
--warmup seconds of its per-transaction log are discarded. Between arms, rows inserted by pgbench
(order_id >= 300,000,000) are deleted and the harness waits until pg_trickle's change backlog is
drained, so every arm starts from the same data size.

Collected per arm: achieved TPS, OLTP latency p50/p95/p99 (per-transaction log), HTTP offered vs
achieved rate, HTTP p50/p95/p99 and errors, lock waits, max CDC backlog, max refresh age, refresh
actions/fallbacks/failures in the window, container CPU/RAM, commit->visible probes (A and B).
Run ONLY against a disposable project.

usage: python3 -I g3_ab.py --project ax-fulltest --port 25671 --api http://127.0.0.1:18191 \
         --pairs 5 --seconds 35 --warmup 5 --http-rate 20 --out results/10k
"""
import argparse
import glob
import json
import os
import random
import statistics
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

HERE = os.path.dirname(os.path.abspath(__file__))
WORKLOAD = os.path.join(HERE, "pgbench_tenants_a.sql")
ap = argparse.ArgumentParser()
ap.add_argument("--project", required=True)
ap.add_argument("--port", type=int, required=True, help="host port of shard A")
ap.add_argument("--api", required=True)
ap.add_argument("--pairs", type=int, default=5)
ap.add_argument("--seconds", type=int, default=35)
ap.add_argument("--warmup", type=int, default=5)
ap.add_argument("--clients", type=int, default=4)
ap.add_argument("--http-rate", type=float, default=20.0, help="fixed offered dashboard requests/s in arm B")
ap.add_argument("--oltp-rate", type=float, default=0.0,
                help="fixed offered OLTP transactions/s (pgbench -R); 0 = unthrottled (saturating)")
ap.add_argument("--seed", type=int, default=int(time.time()))
ap.add_argument("--out", required=True)
ap.add_argument("--orders", type=int, default=10000, help="seed size (for ax_nost) - must match the shard")
args = ap.parse_args()
os.makedirs(args.out, exist_ok=True)
PW = os.environ.get("AX_DB_SUPERUSER_PASSWORD", "local-demo-superuser")
ENV = {**os.environ, "PGPASSWORD": PW}
SHARD_A = f"{args.project}-shard_a-1"
API_C = f"{args.project}-api-1"
rng = random.Random(args.seed)


def psql(db, sql):
    r = subprocess.run(["psql", "-h", "127.0.0.1", "-p", str(args.port), "-U", "postgres", "-d", db, "-XAtq",
                        "-v", "ON_ERROR_STOP=1", "-c", sql], capture_output=True, text=True, env=ENV)
    if r.returncode:
        raise RuntimeError(f"psql {db}: {r.stderr.strip()[:300]}")
    return r.stdout.strip()


def pct(v, q):
    v = sorted(v)
    return round(v[min(len(v) - 1, max(0, int(round(q * len(v))) - 1))], 2) if v else None


# ── no-stream-table database (arm C) ─────────────────────────────────────────
def ensure_nost():
    if psql("postgres", "select count(*) from pg_database where datname='ax_nost'") == "1":
        return
    subprocess.run(["docker", "exec", SHARD_A, "psql", "-U", "postgres", "-d", "postgres", "-qc", "CREATE DATABASE ax_nost"], check=True)
    for f, extra in (("/ax/sql/00_schema.sql", []),
                     ("/ax/seed_shard.sql", ["-v", "tenants={1,3,4}", "-v", f"orders={args.orders}", "-v", "all_tenants=10"]),
                     ("/ax/sql/05_bucket_columns.sql", [])):
        subprocess.run(["docker", "exec", SHARD_A, "psql", "-U", "postgres", "-d", "ax_nost", "-q", "-v", "ON_ERROR_STOP=1",
                        *extra, "-f", f], check=True, capture_output=True)


# Base fixture = every order that is NOT a pgbench row (seed + demo-writer rows). Earlier evidence
# compared A = 5,585 rows with a stale C = 64,501 rows (ax_nost was reused from another run), so the
# A-vs-C maintenance comparison was invalid. Now C is re-synchronised from A before every pair and
# both fingerprints are recorded per arm; a mismatch aborts the run.
FIXTURE_SQL = ("select count(*) || ':' || coalesce(md5(string_agg(order_id || status || quantity || unit_price_cents"
               " || created_at::text, ',' order by tenant_id, order_id)), '') from ax.orders where order_id < 300000000")
DIM_SQL = "select (select count(*) from ax.tenants) || ':' || (select count(*) from ax.products) || ':' || (select count(*) from ax.customers)"


def sync_fixture():
    """Copy arm A's current base rows into ax_nost (no stream tables there, so no CDC side effects)."""
    if psql("aggregatex", DIM_SQL) != psql("ax_nost", DIM_SQL):
        raise RuntimeError("tenants/products/customers differ between aggregatex and ax_nost")
    cols = "tenant_id, order_id, customer_id, product_id, status, quantity, unit_price_cents, created_at, updated_at"
    dump = subprocess.run(["psql", "-h", "127.0.0.1", "-p", str(args.port), "-U", "postgres", "-d", "aggregatex", "-XAtq",
                           "-v", "ON_ERROR_STOP=1", "-c",
                           f"\\copy (select {cols} from ax.orders where order_id < 300000000) to stdout"],
                          capture_output=True, env=ENV, check=True).stdout
    r = subprocess.run(["psql", "-h", "127.0.0.1", "-p", str(args.port), "-U", "postgres", "-d", "ax_nost", "-XAtq",
                        "-v", "ON_ERROR_STOP=1", "-c", "delete from ax.orders", "-c", f"\\copy ax.orders ({cols}) from stdin"],
                       input=dump, capture_output=True, env=ENV)
    if r.returncode:
        raise RuntimeError(f"fixture sync failed: {r.stderr.decode()[:300]}")
    psql("ax_nost", "vacuum (analyze) ax.orders")
    a, c = psql("aggregatex", FIXTURE_SQL), psql("ax_nost", FIXTURE_SQL)
    if a != c:
        raise RuntimeError(f"fixture mismatch after sync: aggregatex={a} ax_nost={c}")
    return a


# ── HTTP dashboard load at a FIXED offered rate ──────────────────────────────
PATHS = [f"/api/tenants/{t}/{e}?from=2026-08-01T00:00:00Z" for t in (1, 3, 4)
         for e in ("summary", "trends", "top-products", "breakdown")]


def login():
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    try:
        op.open(urllib.request.Request(args.api + "/api/auth/login", json.dumps(
            {"email": "admin@demo.local", "password": os.environ.get("AX_DEMO_PASSWORD", "demo1234")}).encode(),
            {"content-type": "application/json"}), timeout=10).read()
    except urllib.error.HTTPError:
        pass
    return op


def http_load(op, seconds, rate, stop, out):
    t0 = time.monotonic()
    n = int(seconds * rate)
    lock = threading.Lock()

    def one(i):
        due = t0 + i / rate
        delay = due - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        if stop.is_set():
            return
        s = time.monotonic()
        try:
            with op.open(args.api + PATHS[i % len(PATHS)], timeout=20) as r:
                r.read()
                code = r.status
        except urllib.error.HTTPError as e:
            code = e.code
        except Exception:  # noqa: BLE001 - transport error counts as an error
            code = 0
        with lock:
            out.append((round((time.monotonic() - s) * 1000, 2), code))
    threads = []
    for i in range(n):            # bounded concurrency: at most 16 in flight
        while sum(t.is_alive() for t in threads) >= 16:
            time.sleep(0.002)
        th = threading.Thread(target=one, args=(i,), daemon=True)
        th.start()
        threads.append(th)
        threads = [t for t in threads if t.is_alive()] + []
    for t in threads:
        t.join(timeout=25)


# ── background samplers ──────────────────────────────────────────────────────
def sampler(db, stop, samples):
    while not stop.is_set():
        try:
            row = psql(db, """select (select count(*) from pg_locks where not granted)
                 || '|' || coalesce((select sum(n_live_tup) from pg_stat_all_tables where schemaname='pgtrickle_changes'),0)
                 || '|' || coalesce((select round(extract(epoch from now()-max(end_time)),1)::text
                                       from pgtrickle.pgt_refresh_history where status='COMPLETED'), '-')""") \
                if db == "aggregatex" else psql(db, "select (select count(*) from pg_locks where not granted)||'|0|-'")
            w, b, a = row.split("|")
            samples.append({"lock_waits": int(w), "cdc_backlog": int(float(b)), "refresh_age_s": None if a == "-" else float(a)})
        except Exception:  # noqa: BLE001
            pass
        stop.wait(2)


def docker_stats():
    r = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}", SHARD_A, API_C],
                       capture_output=True, text=True)
    return {ln.split("|")[0]: {"cpu": ln.split("|")[1], "mem": ln.split("|")[2]} for ln in r.stdout.splitlines() if "|" in ln}


def probe(op, out):
    for action in ("insert", "cancel"):
        body = {"action": action}
        if action == "cancel":
            if not out or not out[-1].get("order_id"):
                return
            body["order_id"] = out[-1]["order_id"]
        try:
            req = urllib.request.Request(args.api + "/api/tenants/3/live-write", json.dumps(body).encode(),
                                         {"content-type": "application/json"})
            d = json.loads(op.open(req, timeout=45).read())
            out.append({"action": action, "order_id": d.get("order_id"), "lag_ms": d.get("lag_ms"), "timed_out": d.get("timed_out")})
        except Exception as exc:  # noqa: BLE001
            out.append({"action": action, "error": str(exc)[:120]})


# ── reset / settle ───────────────────────────────────────────────────────────
def reset(db):
    psql(db, "delete from ax.orders where order_id >= 300000000")
    psql(db, "vacuum (analyze) ax.orders")
    if db != "aggregatex":
        time.sleep(3)
        return
    t0 = time.monotonic()
    while time.monotonic() - t0 < 120:       # wait for CDC backlog to drain and refreshes to catch up
        b = int(float(psql(db, "select coalesce(sum(n_live_tup),0) from pg_stat_all_tables where schemaname='pgtrickle_changes'")))
        age = psql(db, "select round(extract(epoch from now()-max(end_time)),1) from pgtrickle.pgt_refresh_history where status='COMPLETED'")
        if b < 50 and float(age or 99) < 3:
            break
        time.sleep(2)
    time.sleep(5)


# ── one arm ──────────────────────────────────────────────────────────────────
def run_arm(pair, arm, op):
    db = "ax_nost" if arm == "C" else "aggregatex"
    reset(db)
    fixture_rows = int(psql(db, "select count(*) from ax.orders where order_id < 300000000"))
    tmp = tempfile.mkdtemp(prefix=f"g3-{arm}-")
    prefix = os.path.join(tmp, "tx")
    stop = threading.Event()
    samples, http, probes = [], [], []
    st = threading.Thread(target=sampler, args=(db, stop, samples), daemon=True)
    st.start()
    ht = None
    if arm == "B":
        ht = threading.Thread(target=http_load, args=(op, args.seconds, args.http_rate, stop, http), daemon=True)
        ht.start()
    pt = None
    if arm in ("A", "B"):
        pt = threading.Timer(args.warmup + 5, probe, args=(op, probes))
        pt.start()
    stats_holder = {}
    threading.Timer(args.seconds / 2, lambda: stats_holder.update(docker_stats())).start()
    t_start = time.time()
    pb = subprocess.run(["pgbench", "-h", "127.0.0.1", "-p", str(args.port), "-U", "postgres", "-n",
                         "-c", str(args.clients), "-j", "2", "-T", str(args.seconds), "-f", WORKLOAD,
                         *(["-R", str(args.oltp_rate)] if args.oltp_rate > 0 else []),
                         "-l", "--log-prefix", prefix, db], capture_output=True, text=True, env=ENV, cwd=tmp)
    t_end = time.time()
    if ht:
        ht.join(timeout=30)
    if pt:
        pt.join(timeout=60)
    stop.set()
    st.join(timeout=5)
    lat, n_meas = [], 0
    for f in glob.glob(prefix + "*"):
        for ln in open(f):
            p = ln.split()
            if len(p) >= 6 and float(p[4]) >= t_start + args.warmup:
                lat.append(int(p[2]) / 1000.0)
    meas_s = (t_end - t_start) - args.warmup
    hist = {}
    if db == "aggregatex":
        rows = psql(db, f"""select action || ':' || count(*) || ':' || count(*) filter (where was_full_fallback)
                                || ':' || count(*) filter (where status='FAILED')
                              from pgtrickle.pgt_refresh_history
                             where start_time >= to_timestamp({t_start}) and start_time < to_timestamp({t_end})
                             group by action""")
        for r in rows.splitlines():
            a, n, fb, fl = r.split(":")
            hist[a] = {"n": int(n), "fallbacks": int(fb), "failed": int(fl)}
    hl = [x[0] for x in http if 200 <= x[1] < 300]
    res = {
        "pair": pair, "arm": arm, "db": db, "fixture_rows": fixture_rows, "start": t_start, "seconds_measured": round(meas_s, 1),
        "pgbench_exit": pb.returncode, "pgbench_failed_line": next((l for l in pb.stdout.splitlines() if "failed" in l), ""),
        "tps": round(len(lat) / meas_s, 1) if meas_s > 0 else None,
        "oltp_offered_tps": args.oltp_rate or None,
        "lat_ms": {"p50": pct(lat, .5), "p95": pct(lat, .95), "p99": pct(lat, .99), "mean": round(statistics.mean(lat), 3) if lat else None},
        "http": None if arm != "B" else {
            "offered_rps": args.http_rate, "achieved_rps": round(len(http) / args.seconds, 1),
            "ok": len(hl), "errors": sum(1 for x in http if not 200 <= x[1] < 300),
            "status_counts": {str(c): sum(1 for x in http if x[1] == c) for c in sorted({x[1] for x in http})},
            "p50": pct(hl, .5), "p95": pct(hl, .95), "p99": pct(hl, .99)},
        "lock_waits_max": max((s["lock_waits"] for s in samples), default=0),
        "cdc_backlog_max": max((s["cdc_backlog"] for s in samples), default=0),
        "refresh_age_max_s": max((s["refresh_age_s"] for s in samples if s["refresh_age_s"] is not None), default=None),
        "refresh_history": hist, "docker": stats_holder, "probes": probes,
    }
    with open(os.path.join(args.out, "arms.jsonl"), "a") as fh:
        fh.write(json.dumps(res) + "\n")
    print(f"pair {pair} arm {arm}: tps={res['tps']} p50={res['lat_ms']['p50']} p95={res['lat_ms']['p95']} "
          f"p99={res['lat_ms']['p99']} http={res['http'] and (res['http']['achieved_rps'], res['http']['errors'], res['http']['p95'])} "
          f"backlog_max={res['cdc_backlog_max']} age_max={res['refresh_age_max_s']} probes={[(p.get('action'), p.get('lag_ms')) for p in probes]}",
          flush=True)
    return res


def main():
    meta = {"args": vars(args), "workload": open(WORKLOAD).read(), "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    ensure_nost()
    meta["rows"] = {db: psql(db, "select count(*) from ax.orders") for db in ("aggregatex", "ax_nost")}
    meta["versions"] = psql("aggregatex", "select version() || ' | pg_trickle ' || extversion from pg_extension where extname='pg_trickle'")
    json.dump(meta, open(os.path.join(args.out, "meta.json"), "w"), indent=1)
    op = login()
    results = []
    for p in range(1, args.pairs + 1):
        order = ["A", "B", "C"]
        rng.shuffle(order)
        # Pause the demo writer for the 1-2 s copy so both fingerprints come from one state
        # (the first matched run aborted at pair 3 on a 1-row race: 5,392 vs 5,391).
        subprocess.run(["docker", "stop", f"{args.project}-writer-1"], capture_output=True)
        try:
            meta.setdefault("fixture_per_pair", {})[p] = sync_fixture()
        finally:
            subprocess.run(["docker", "start", f"{args.project}-writer-1"], capture_output=True)
        json.dump(meta, open(os.path.join(args.out, "meta.json"), "w"), indent=1)
        for arm in order:
            results.append(run_arm(p, arm, op))
    by = {a: [r for r in results if r["arm"] == a] for a in "ABC"}
    pairs = []
    for p in range(1, args.pairs + 1):
        a, b, c = (next(r for r in by[x] if r["pair"] == p) for x in "ABC")
        pairs.append({"pair": p,
                      "B_vs_A_tps_pct": round((b["tps"] - a["tps"]) / a["tps"] * 100, 1),
                      "B_vs_A_p95_pct": round((b["lat_ms"]["p95"] - a["lat_ms"]["p95"]) / a["lat_ms"]["p95"] * 100, 1),
                      "A_vs_C_tps_pct": round((a["tps"] - c["tps"]) / c["tps"] * 100, 1),
                      "A_vs_C_p95_pct": round((a["lat_ms"]["p95"] - c["lat_ms"]["p95"]) / c["lat_ms"]["p95"] * 100, 1)})
    summ = {k: {"median": statistics.median(x[k] for x in pairs), "min": min(x[k] for x in pairs), "max": max(x[k] for x in pairs)}
            for k in ("B_vs_A_tps_pct", "B_vs_A_p95_pct", "A_vs_C_tps_pct", "A_vs_C_p95_pct")}
    # Quiesced exact oracle of all three stream tables (writer paused, then restored).
    writer = f"{args.project}-writer-1"
    subprocess.run(["docker", "stop", writer], capture_output=True)
    try:
        reset("aggregatex")
        time.sleep(10)
        oracle = psql("aggregatex", "select string_agg(stream_table || '=' || missing_in_st || '/' || extra_in_st, ' '"
                                    " order by stream_table) from ax.oracle_mismatches()")
    finally:
        subprocess.run(["docker", "start", writer], capture_output=True)
    fixture_rows = {x: sorted({r["fixture_rows"] for r in by[x]}) for x in "ABC"}
    out = {"pairs": pairs, "summary": summ, "seed": args.seed,
           "median_tps": {x: statistics.median(r["tps"] for r in by[x]) for x in "ABC"},
           "median_p95_ms": {x: statistics.median(r["lat_ms"]["p95"] for r in by[x]) for x in "ABC"},
           "fixture_rows_per_arm": fixture_rows,
           "fallbacks_A_B": sum(v["fallbacks"] for r in by["A"] + by["B"] for v in (r.get("refresh_history") or {}).values()
                                if isinstance(v, dict)),
           "oracle_quiesced": oracle}
    json.dump(out, open(os.path.join(args.out, "summary.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
