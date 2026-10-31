"""Paired mixed-OLTP safety experiment, executed inside the API container."""
import json
import os
import random
import statistics
import threading
import time
from collections import Counter

import httpx
import psycopg
from psycopg.rows import dict_row

secrets = json.load(open("secrets.json"))
database_url = os.environ["DATABASE_URL"]  # restricted API role, includes RLS
admin_url = os.environ["ADMIN_DATABASE_URL"]
TENANTS = (1, 2, 3, 10)
PAIRS = 8
OPS_PER_ARM = 120
TARGET_DASHBOARD_RPS = 20
TARGET_OLTP_RPS = 40
MARKER_CENTS = 987654321
MARKER_FROM = "2099-01-01T00:00:00Z"
MARKER_TO = "2100-01-01T00:00:00Z"
SAMPLE_ORDERS = []
INSERTED_ORDERS = []
samples = []
arms = []
errors = []


def emit_phase(pair, dashboard, state):
    print("@@PHASE " + json.dumps({"pair": pair, "dashboard": dashboard, "state": state}), flush=True)


def pct(values, fraction):
    values = sorted(values)
    return values[min(len(values) - 1, int(len(values) * fraction))]


def metric(values):
    return {"n": len(values), "mean": statistics.mean(values), "p50": statistics.median(values),
            "p95": pct(values, .95), "p99": pct(values, .99), "max": max(values)}


def seed_rows(conn):
    ids = []
    for tenant in TENANTS:
        for j in range(12):
            product = 1 + (j % 32)
            category = 1 + ((product - 1) % 8)
            order_id = conn.execute(
                "INSERT INTO orders(tenant_id,customer_id,product_id,category_id,ordered_at,status,quantity,unit_price_cents) "
                "VALUES(%s,100,%s,%s,%s,'placed',1,%s) RETURNING id",
                (tenant, product, category, f"2099-01-{1 + j % 28:02d}T00:00:00Z", MARKER_CENTS),
            ).fetchone()["id"]
            ids.append({"tenant": tenant, "id": order_id})
    return ids


def dashboard_worker(stop_event, state, sample_lock, worker_index):
    families = ("summary", "trends", "top-products", "breakdown")
    # One fixed tenant per worker avoids intentionally tripping the API's
    # per-tenant concurrency guard while still driving four concurrent tenants.
    tenant = TENANTS[worker_index % len(TENANTS)]
    family_index = 0
    n = 0
    failures = []
    latencies = []
    start_gate = state["gate"]
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=10) as client:
        while not stop_event.is_set():
            start_gate.wait()
            if stop_event.is_set():
                break
            family = families[family_index % len(families)]
            family_index += 1
            began = time.perf_counter()
            try:
                response = client.get(
                    f"/tenants/{tenant}/{family}?from=2026-10-01T05:13:17Z&to=2026-10-08T18:29:11Z",
                    headers={"Authorization": "Bearer " + secrets["tenants"][str(tenant)]},
                )
                elapsed = (time.perf_counter() - began) * 1000
                if response.status_code != 200:
                    failures.append({"status": response.status_code})
            except Exception as exc:
                elapsed = (time.perf_counter() - began) * 1000
                failures.append({"error": type(exc).__name__})
            with sample_lock:
                n += 1
                latencies.append(elapsed)
            stop_event.wait(max(0, 0.2 - (time.perf_counter() - began)))
    return {"requests": n, "errors": failures, "latencies_ms": latencies}


def planned_workload(seed, update_ids):
    rng = random.Random(seed)
    operations = (["select"] * (OPS_PER_ARM // 2) +
                  ["update"] * (OPS_PER_ARM // 4) +
                  ["insert"] * (OPS_PER_ARM // 4))
    rng.shuffle(operations)
    by_tenant = {tenant: [x["id"] for x in update_ids if x["tenant"] == tenant] for tenant in TENANTS}
    workload = []
    for kind in operations:
        tenant = rng.choices(TENANTS, weights=(4, 2, 1, 1), k=1)[0]
        workload.append({"kind": kind, "tenant": tenant,
                         "update_id": rng.choice(by_tenant[tenant]) if kind == "update" else None})
    return workload


def execute_arm(pair, dashboard, workload, fixture_ids):
    emit_phase(pair, dashboard, "start")
    stop = threading.Event()
    gate = threading.Event()
    state = {"gate": gate}
    sample_lock = threading.Lock()
    worker_results = []
    workers = []
    if dashboard:
        with httpx.Client(base_url="http://127.0.0.1:8000", timeout=10) as warm:
            for tenant in TENANTS:
                warm.get(f"/tenants/{tenant}/summary?from=2026-10-01T00:00Z&to=2026-10-02T00:00Z",
                         headers={"Authorization": "Bearer " + secrets["tenants"][str(tenant)]}).raise_for_status()
        workers = [threading.Thread(target=lambda i=i: worker_results.append(dashboard_worker(stop, state, sample_lock, i))) for i in range(4)]
        for worker in workers:
            worker.start()
        time.sleep(1.0)  # warm the API clients before the measured window
    arm_started = time.perf_counter()
    gate.set()
    completed = 0
    type_counts = Counter()
    operation_conn = psycopg.connect(database_url, autocommit=True, row_factory=dict_row)
    try:
        for operation in workload:
            began = time.perf_counter()
            tenant, kind = operation["tenant"], operation["kind"]
            operation_conn.execute("BEGIN")
            operation_conn.execute("SELECT set_config('app.tenant',%s,true)", (str(tenant),))
            statement_started = time.perf_counter()
            if kind == "select":
                order_id = next((x["id"] for x in fixture_ids if x["tenant"] == tenant), None)
                operation_conn.execute("SELECT id,status,quantity,unit_price_cents FROM orders WHERE tenant_id=%s AND id=%s", (tenant, order_id)).fetchone()
            elif kind == "update":
                operation_conn.execute("UPDATE orders SET quantity=CASE WHEN quantity=1 THEN 2 ELSE 1 END,version=version+1 WHERE tenant_id=%s AND id=%s", (tenant, operation["update_id"]))
            else:
                product = 1 + (completed % 32)
                category = 1 + ((product - 1) % 8)
                order_id = operation_conn.execute(
                    "INSERT INTO orders(tenant_id,customer_id,product_id,category_id,ordered_at,status,quantity,unit_price_cents) "
                    "VALUES(%s,100,%s,%s,%s,'placed',1,%s) RETURNING id",
                    (tenant, product, category, f"2099-01-{1 + completed % 28:02d}T00:00:00Z", MARKER_CENTS),
                ).fetchone()["id"]
                INSERTED_ORDERS.append(order_id)
            statement_ms = (time.perf_counter() - statement_started) * 1000
            commit_started = time.perf_counter()
            operation_conn.execute("COMMIT")
            commit_ms = (time.perf_counter() - commit_started) * 1000
            transaction_ms = (time.perf_counter() - began) * 1000
            samples.append({"pair": pair, "dashboard": dashboard, "kind": kind,
                            "statement_ms": statement_ms, "commit_ms": commit_ms,
                            "transaction_ms": transaction_ms})
            completed += 1
            type_counts[kind] += 1
            time.sleep(max(0, 1 / TARGET_OLTP_RPS - (time.perf_counter() - began)))
    finally:
        operation_conn.close()
        if dashboard:
            stop.set()
            for worker in workers:
                worker.join(timeout=15)
    elapsed = time.perf_counter() - arm_started
    dashboard_data = {"requests": sum(x["requests"] for x in worker_results),
                      "errors": [err for x in worker_results for err in x["errors"]],
                      "latencies_ms": [v for x in worker_results for v in x["latencies_ms"]]}
    arm = {"pair": pair, "dashboard": dashboard, "operations": completed,
           "elapsed_seconds": elapsed, "operational_actual_rps": completed / elapsed,
           "operation_counts": dict(type_counts),
           "dashboard_requests": dashboard_data["requests"],
           "dashboard_actual_rps": dashboard_data["requests"] / elapsed if dashboard else 0,
           "dashboard_errors": len(dashboard_data["errors"]),
           "dashboard_error_samples": dashboard_data["errors"][:20],
           "dashboard_latency_ms": metric(dashboard_data["latencies_ms"]) if dashboard_data["latencies_ms"] else None}
    arms.append(arm)
    emit_phase(pair, dashboard, "end")
    return arm


def main():
    with psycopg.connect(admin_url, row_factory=dict_row, autocommit=True) as admin:
        marker_count = admin.execute(
            "SELECT count(*) FROM orders WHERE ordered_at >= %s::timestamptz AND ordered_at < %s::timestamptz AND customer_id=100 AND unit_price_cents=%s",
            (MARKER_FROM, MARKER_TO, MARKER_CENTS),
        ).fetchone()["count"]
        if marker_count:
            raise RuntimeError(f"Safety fixture marker already exists ({marker_count} rows); refusing to touch it")
        historical_test_rows = admin.execute(
            "SELECT count(*) FROM orders WHERE ordered_at >= %s::timestamptz AND ordered_at < %s::timestamptz",
            (MARKER_FROM, MARKER_TO),
        ).fetchone()["count"]
        if historical_test_rows:
            raise RuntimeError(f"Safety test date range is not empty ({historical_test_rows} orders); refusing fixture cleanup")
        baseline = admin.execute("SELECT count(*) AS orders,coalesce(sum(quantity::bigint*unit_price_cents),0)::text AS gross_cents FROM orders").fetchone()
        try:
            seed_ids = seed_rows(admin)
            SAMPLE_ORDERS.extend(seed_ids)
            for pair in range(PAIRS):
                workload = planned_workload(481516 + pair, seed_ids)
                arm_order = [False, True]
                random.Random(73129 + pair).shuffle(arm_order)
                for dashboard in arm_order:
                    execute_arm(pair, dashboard, workload, seed_ids)
        finally:
            ids = [x["id"] for x in SAMPLE_ORDERS] + INSERTED_ORDERS
            if ids:
                admin.execute("DELETE FROM orders WHERE id = ANY(%s)", (ids,))
            remaining = admin.execute(
                "SELECT count(*) FROM orders WHERE ordered_at >= %s::timestamptz AND ordered_at < %s::timestamptz",
                (MARKER_FROM, MARKER_TO),
            ).fetchone()["count"]
            if remaining:
                raise RuntimeError(f"Safety fixtures remain in the reserved test range ({remaining} rows); rollups retained")
            admin.execute(
                "DELETE FROM daily_product WHERE bucket >= %s::timestamptz AND bucket < %s::timestamptz AND n=0 AND units=0 AND cents=0",
                (MARKER_FROM, MARKER_TO),
            )
            admin.execute(
                "DELETE FROM hourly_category WHERE bucket >= %s::timestamptz AND bucket < %s::timestamptz AND n=0 AND units=0 AND cents=0",
                (MARKER_FROM, MARKER_TO),
            )
        after = admin.execute("SELECT count(*) AS orders,coalesce(sum(quantity::bigint*unit_price_cents),0)::text AS gross_cents FROM orders").fetchone()
    groups = {}
    for metric_name in ("statement_ms", "commit_ms", "transaction_ms"):
        groups[metric_name] = {}
        for kind in ("select", "update", "insert"):
            groups[metric_name][kind] = {}
            for loaded in (False, True):
                values = [x[metric_name] for x in samples if x["kind"] == kind and x["dashboard"] == loaded]
                groups[metric_name][kind]["dashboard" if loaded else "baseline"] = metric(values)
    totals = {}
    for metric_name in ("statement_ms", "commit_ms", "transaction_ms"):
        totals[metric_name] = {}
        for loaded in (False, True):
            values = [x[metric_name] for x in samples if x["dashboard"] == loaded]
            totals[metric_name]["dashboard" if loaded else "baseline"] = metric(values)
        baseline_mean = totals[metric_name]["baseline"]["mean"]
        loaded_mean = totals[metric_name]["dashboard"]["mean"]
        baseline_p95 = totals[metric_name]["baseline"]["p95"]
        loaded_p95 = totals[metric_name]["dashboard"]["p95"]
        totals[metric_name]["mean_slowdown_percent"] = (loaded_mean / baseline_mean - 1) * 100
        totals[metric_name]["p95_slowdown_percent"] = (loaded_p95 / baseline_p95 - 1) * 100
    target_ok = all(v["mean_slowdown_percent"] < 10 and v["p95_slowdown_percent"] < 10 for v in totals.values())
    errors_total = sum(x["dashboard_errors"] for x in arms)
    throughput_ok = all(x["operational_actual_rps"] >= TARGET_OLTP_RPS * .9 for x in arms)
    loaded_arms = [x for x in arms if x["dashboard"]]
    throughput_ok = throughput_ok and all(x["dashboard_actual_rps"] >= TARGET_DASHBOARD_RPS * .9 for x in loaded_arms)
    out = {"schema_version": 2, "status": "PASS" if target_ok and throughput_ok and errors_total == 0 else "FAIL",
           "pairs": PAIRS, "operations_per_arm": PAIRS * OPS_PER_ARM,
           "operations_per_pair_arm": OPS_PER_ARM, "dashboard_rps_target": TARGET_DASHBOARD_RPS,
           "dashboard_clients": 4, "operational_rps_target": TARGET_OLTP_RPS,
           "operation_mix_per_arm": {"select": .5, "update": .25, "insert": .25},
           "operation_metrics": groups, "metrics": totals, "arms": arms, "samples": samples,
           "dashboard_errors": errors_total, "operational_errors": 0,
           "throughput_target_met": throughput_ok,
           "randomization": "Eight pair-specific fixed-seed workload sequences; baseline/dashboard arm order randomized within each pair.",
           "source_cleanup_verified": baseline == after,
           "source_before": dict(baseline), "source_after": dict(after),
           "status_note": "G-3 applies to achieved mixed-transaction workload; statement, COMMIT round-trip and full transaction times are separated."}
    print(json.dumps(out), flush=True)


main()
