#!/usr/bin/env python3
"""Reproducible HTTP distributions, stable-source oracle and exact rollup checks."""
import concurrent.futures
import datetime
import json
import os
import platform
import statistics
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from db import ROOT, query_json, sql
sys.path.insert(0, str(Path(__file__).parent))
from functional import direct, headers
from validation import FAMILIES, RANGES, expected_correctness_coverage, source_snapshot

BASE = "http://127.0.0.1:18081"
RANGE_VALUES = {
    "day": ("2026-10-01T00:00:00Z", "2026-10-02T00:00:00Z"),
    "week": ("2026-10-01T00:00:00Z", "2026-10-08T00:00:00Z"),
    "month": ("2026-10-01T00:00:00Z", "2026-10-31T00:00:00Z"),
    "boundary": ("2026-10-01T05:13:17.123Z", "2026-10-08T18:29:11.456Z"),
}


def dataset_metadata(scale):
    manifest_file = os.environ.get("AGRREGATEX_DATASET_MANIFEST")
    if manifest_file:
        raw = json.loads(Path(manifest_file).read_text())
    else:
        manifest_exists = query_json("SELECT to_regclass('loader.dataset_manifest') IS NOT NULL AS present")[0]["present"]
        raw = query_json("SELECT manifest FROM loader.dataset_manifest LIMIT 1")[0]["manifest"] if manifest_exists else None
    if isinstance(raw, dict) and isinstance(raw.get("manifest"), dict):
        raw = raw["manifest"]
    if isinstance(raw, dict):
        generator = raw.get("generator_id") or raw.get("generator")
        seed = raw.get("seed")
        dataset_id = raw.get("dataset_id") or (f"{generator}-seed-{seed}" if generator is not None and seed is not None else None)
        return {
            "dataset_id": dataset_id,
            "generator_id": generator,
            "generator_version": raw.get("generator_version"),
            "seed": seed,
            "official_compatibility": raw.get("official_compatibility", raw.get("official_dataset_compatibility")),
            "manifest_version": raw.get("manifest_version"),
            "loader_manifest": raw,
            "loader_run_id": raw.get("run_id"),
            "load_completed_at": raw.get("load_completed_at"),
        }
    if scale == 1_000_000:
        return {"dataset_id": "representative-seed42-v1", "generator_id": "agrregatex-representative-v1",
                "generator_version": "not-recorded", "seed": 42,
                "official_compatibility": "NOT_VERIFIED", "manifest_version": 1,
                "loader_manifest": None, "loader_run_id": None, "load_completed_at": None}
    return {"dataset_id": None, "generator_id": None, "generator_version": None, "seed": None,
            "official_compatibility": "NOT_VERIFIED", "manifest_version": None,
            "loader_manifest": None, "loader_run_id": None, "load_completed_at": None}


def git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return None


def server_version():
    return query_json("SELECT version() AS version")[0]["version"]


def cpu_model():
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine()


def path(tenant, family, start, end, grain):
    return f"/tenants/{tenant}/{family}?from={start}&to={end}&grain={grain}"


def hit(client, tenant, family, grain, range_name, mode):
    start, end = RANGE_VALUES[range_name]
    began = time.perf_counter()
    try:
        response = client.get(path(tenant, family, start, end, grain), headers=headers(tenant))
        status, error = response.status_code, None
    except Exception as exc:
        status, error = None, type(exc).__name__
    return {"tenant": tenant, "family": family, "grain": grain, "range": range_name,
            "mode": mode, "ms": (time.perf_counter() - began) * 1000,
            "http": status, "error": error}


def metrics(values):
    if not values:
        return {"n": 0, "p50": None, "p95": None, "p99": None, "max": None, "mean": None}
    values = sorted(values)
    return {"n": len(values), "p50": statistics.median(values),
            "p95": values[min(len(values) - 1, int(len(values) * .95))],
            "p99": values[min(len(values) - 1, int(len(values) * .99))],
            "max": max(values), "mean": statistics.mean(values)}


def main():
    if len(sys.argv) != 2 or int(sys.argv[1]) not in (1_000_000, 10_000_000):
        raise SystemExit("Usage: python3 benchmarks/run.py 1000000|10000000")
    scale = int(sys.argv[1])
    tenant_count = 10 if scale == 1_000_000 else 100
    started = datetime.datetime.now(datetime.timezone.utc)
    before = source_snapshot(query_json)
    if before["order_count"] != scale or before["tenant_count"] != tenant_count or before["populated_tenant_count"] != tenant_count:
        raise SystemExit(f"Refusing benchmark: expected {scale} source rows and {tenant_count} populated tenants; got {before['order_count']} rows, {before['tenant_count']} tenants, {before['populated_tenant_count']} populated.")
    data = dataset_metadata(scale)
    loader_manifest = data.get("loader_manifest")
    if scale == 10_000_000 and not loader_manifest:
        raise SystemExit("Refusing 10M benchmark without a loader.dataset_manifest or AGRREGATEX_DATASET_MANIFEST")
    if loader_manifest:
        if loader_manifest.get("source_rows") != before["order_count"] or loader_manifest.get("tenant_count") != before["tenant_count"]:
            raise SystemExit("Loader manifest source_rows/tenant_count does not match the live source snapshot")
        manifest_distribution = loader_manifest.get("tenant_distribution")
        if not isinstance(manifest_distribution, list):
            raise SystemExit("Loader manifest tenant_distribution is missing")
        expected_distribution = {row["tenant_id"]: row["orders"] for row in before["tenant_distribution"]}
        try:
            supplied_distribution = {row["tenant_id"]: row.get("rows") for row in manifest_distribution}
        except (KeyError, TypeError):
            raise SystemExit("Loader manifest tenant_distribution is malformed")
        if supplied_distribution != expected_distribution:
            raise SystemExit("Loader manifest tenant_distribution does not match live source rows")
    if os.environ.get("AGRREGATEX_DATASET_MANIFEST") and not all(data.get(k) is not None for k in ("dataset_id", "generator_id", "generator_version", "seed", "official_compatibility")):
        raise SystemExit("Dataset manifest is missing required dataset/generator/version/seed/official_compatibility fields")
    out = {
        "schema_version": 2, "scale": scale,
        "dataset": data,
        "run": {"run_id": uuid.uuid4().hex, "started_at_utc": started.isoformat(),
                "git_commit": git_commit(), "postgres_version": server_version()},
        "hardware": {"platform": platform.platform(), "machine": platform.machine(),
                     "processor": cpu_model(), "logical_cpus": os.cpu_count(),
                     "ram_bytes": os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")},
        "workload": {"ranges": list(RANGES), "range_parameters": RANGE_VALUES,
                     "families": [list(x) for x in FAMILIES], "sequential_repeats": 8,
                     "concurrent_clients": 4, "concurrent_rounds": 3,
                     "api_base_url": BASE, "timezone": "UTC", "time_range_semantics": "[from,to)",
                     "top_n_limit": 10,
                     "sequential_tenant_roles": {"hot": 1, "second": 2, "small": tenant_count},
                     "concurrent_tenant_roles": {"hot": 1, "second": 2, "middle": 3, "small": tenant_count}},
        "source_snapshot": before, "requests": [], "correctness": [], "freshness": [],
        "oracle_consistency": {"relation": "public.orders", "lock_mode": "SHARE",
                               "lock_acquired": False, "comparison_count": 0},
    }
    lock = None
    with httpx.Client(base_url=BASE, timeout=30) as client:
        # Warm cache separately and retain only the fixed-size measurement matrix.
        for tenant in (1, 2, tenant_count):
            for range_name in RANGES:
                for family, grain in FAMILIES:
                    hit(client, tenant, family, grain, range_name, "warmup")
                    for _ in range(8):
                        out["requests"].append(hit(client, tenant, family, grain, range_name, "sequential"))

        def concurrent_run(tenant):
            results = []
            with httpx.Client(base_url=BASE, timeout=30) as concurrent_client:
                for _ in range(3):
                    for range_name in RANGES:
                        for family, grain in FAMILIES:
                            results.append(hit(concurrent_client, tenant, family, grain, range_name, "concurrent4"))
            return results

        with concurrent.futures.ThreadPoolExecutor(4) as executor:
            for result in executor.map(concurrent_run, (1, 2, 3, tenant_count)):
                out["requests"].extend(result)

        # SHARE permits dashboard reads but blocks concurrent source writes so
        # each API observation and its direct SQL oracle see the same state.
        lock = subprocess.Popen(
            ["podman", "exec", "-i", "agrregatex-postgres-1", "psql", "-X", "-qAt",
             "-v", "ON_ERROR_STOP=1", "-U", "agrregatex_owner", "-d", "agrregatex"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
        lock.stdin.write("BEGIN; LOCK TABLE public.orders IN SHARE MODE; SELECT 'AGRREGATEX_LOCK_ACQUIRED';\n")
        lock.stdin.flush()
        marker = lock.stdout.readline().strip()
        if marker != "AGRREGATEX_LOCK_ACQUIRED":
            lock.kill()
            raise RuntimeError("Could not acquire source stability lock: " + lock.stderr.read())
        out["oracle_consistency"]["lock_acquired"] = True
        try:
            expected = expected_correctness_coverage(scale)
            for tenant, family, grain, range_name in sorted(expected):
                start, end = RANGE_VALUES[range_name]
                response = client.get(path(tenant, family, start, end, grain), headers=headers(tenant))
                actual = response.json().get("data") if response.status_code == 200 else None
                oracle = direct(tenant, start, end, family, grain)
                out["correctness"].append({"tenant": tenant, "family": family, "grain": grain,
                                           "range": range_name,
                                           "status": "PASS" if response.status_code == 200 and actual == oracle else "FAIL",
                                           **({"actual": actual, "expected": oracle, "http": response.status_code}
                                              if response.status_code != 200 or actual != oracle else {})})
        finally:
            lock.stdin.write("ROLLBACK;\n")
            lock.stdin.close()
            lock.wait(timeout=20)
            if lock.returncode:
                raise RuntimeError("Source stability lock psql exited unexpectedly: " + lock.stderr.read())
        out["oracle_consistency"]["comparison_count"] = len(out["correctness"])

        for iteration in range(5):
            test_order_id = None
            try:
                before_summary = client.get(path(1, "summary", "2027-01-01T00:00:00Z", "2027-01-02T00:00:00Z", "day"), headers=headers(1)).json()["data"]
                started_mutation = time.perf_counter()
                test_order_id = int(sql("INSERT INTO orders(tenant_id,customer_id,product_id,category_id,ordered_at,status,quantity,unit_price_cents) VALUES(1,1,1,1,'2027-01-01T12:34:56Z','placed',2,1234) RETURNING id;"))
                mutations = [
                    ("insert", None, before_summary["orders"] + 1, before_summary["sales_cents"] + 2468),
                    ("update", f"UPDATE orders SET quantity=3,unit_price_cents=2222 WHERE tenant_id=1 AND id={test_order_id};", before_summary["orders"] + 1, before_summary["sales_cents"] + 6666),
                    ("cancel", f"UPDATE orders SET status='cancelled' WHERE tenant_id=1 AND id={test_order_id};", before_summary["orders"] + 1, before_summary["sales_cents"]),
                ]
                for operation, statement, expected_orders, expected_cents in mutations:
                    started_op = time.perf_counter()
                    if statement:
                        sql(statement)
                    commit_observed = time.perf_counter()
                    for _ in range(300):
                        response = client.get(path(1, "summary", "2027-01-01T00:00:00Z", "2027-01-02T00:00:00Z", "day"), headers=headers(1))
                        observed = response.json()["data"] if response.status_code == 200 else {}
                        if observed.get("orders") == expected_orders and observed.get("sales_cents") == expected_cents:
                            break
                        time.sleep(.1)
                    passed = observed.get("orders") == expected_orders and observed.get("sales_cents") == expected_cents
                    out["freshness"].append({"operation": operation, "iteration": iteration,
                                             "post_commit_observation_seconds": time.perf_counter() - commit_observed,
                                             "including_sql_roundtrip_seconds": time.perf_counter() - (started_mutation if operation == "insert" else started_op),
                                             "status": "PASS" if passed else "FAIL"})
            finally:
                if test_order_id is not None:
                    sql(f"DELETE FROM orders WHERE tenant_id=1 AND id={test_order_id};")

    out["rollup_mismatches"] = query_json("""SELECT 'daily_product' name,count(*) mismatches FROM (
      (SELECT tenant_id,bucket,product_id,category_id,status,n,units,cents FROM daily_product WHERE n<>0
       EXCEPT ALL SELECT tenant_id,date_trunc('day',ordered_at,'UTC'),product_id,category_id,status,count(*),sum(quantity),sum(quantity::bigint*unit_price_cents) FROM orders GROUP BY 1,2,3,4,5)
      UNION ALL
      (SELECT tenant_id,date_trunc('day',ordered_at,'UTC'),product_id,category_id,status,count(*),sum(quantity),sum(quantity::bigint*unit_price_cents) FROM orders GROUP BY 1,2,3,4,5
       EXCEPT ALL SELECT tenant_id,bucket,product_id,category_id,status,n,units,cents FROM daily_product WHERE n<>0)) d
      UNION ALL SELECT 'hourly_category',count(*) FROM (
      (SELECT tenant_id,bucket,category_id,status,n,units,cents FROM hourly_category WHERE n<>0
       EXCEPT ALL SELECT tenant_id,date_trunc('hour',ordered_at,'UTC'),category_id,status,count(*),sum(quantity),sum(quantity::bigint*unit_price_cents) FROM orders GROUP BY 1,2,3,4)
      UNION ALL
      (SELECT tenant_id,date_trunc('hour',ordered_at,'UTC'),category_id,status,count(*),sum(quantity),sum(quantity::bigint*unit_price_cents) FROM orders GROUP BY 1,2,3,4
       EXCEPT ALL SELECT tenant_id,bucket,category_id,status,n,units,cents FROM hourly_category WHERE n<>0)) d""")
    out["source_snapshot_after"] = source_snapshot(query_json)
    out["baseline_cleanup_verified"] = out["source_snapshot_after"] == before
    out["errors"] = sum(request.get("http") != 200 for request in out["requests"])
    out["latency"] = {}
    for family, grain in FAMILIES:
        for mode in ("sequential", "concurrent4"):
            values = [x["ms"] for x in out["requests"] if x["family"] == family and x["grain"] == grain and x["mode"] == mode and x["http"] == 200]
            out["latency"][f"{family}:{grain}:{mode}"] = metrics(values)
    out["query_target"] = "PASS" if out["errors"] == 0 and max((x["ms"] for x in out["requests"]), default=float("inf")) < 200 else "FAIL"
    out["correctness_target"] = "PASS" if out["correctness"] and all(x["status"] == "PASS" for x in out["correctness"]) and len(out["correctness"]) == sum(expected_correctness_coverage(scale).values()) and {x["name"] for x in out["rollup_mismatches"]} == {"daily_product", "hourly_category"} and all(x["mismatches"] == 0 for x in out["rollup_mismatches"]) else "FAIL"
    out["run"]["finished_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    out["runner_status"] = "COMPLETED"
    RESULTS = ROOT / "benchmarks/results"
    result_file = RESULTS / f"benchmark-{scale}.json"
    result_file.write_text(json.dumps(out, indent=2))
    print(json.dumps({k: v for k, v in out.items() if k not in ("requests", "correctness", "freshness")}, indent=2))


if __name__ == "__main__":
    main()
