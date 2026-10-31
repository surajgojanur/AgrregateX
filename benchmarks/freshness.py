#!/usr/bin/env python3
"""Measure source commit timestamp to correct tenant API visibility."""
import datetime
import json
import platform
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from db import ROOT, query_json, sql
sys.path.insert(0, str(Path(__file__).parent))
from functional import headers
from validation import source_snapshot


def main():
    scale = int(sys.argv[1])
    if scale not in (1_000_000, 10_000_000):
        raise SystemExit("scale must be 1000000 or 10000000")
    before = source_snapshot(query_json)
    expected_tenants = 10 if scale == 1_000_000 else 100
    if before["order_count"] != scale or before["tenant_count"] != expected_tenants:
        raise SystemExit("Refusing freshness test on unexpected source scale")
    run_id = uuid.uuid4().hex
    started = datetime.datetime.now(datetime.timezone.utc)
    samples = []
    with httpx.Client(base_url="http://127.0.0.1:18081") as client:
        for iteration in range(10):
            order_id = None
            try:
                for operation, quantity, status in (("insert", 2, "placed"), ("update", 3, "placed"), ("cancel", 3, "cancelled")):
                    start = time.monotonic()
                    if operation == "insert":
                        order_id = int(sql("INSERT INTO orders(tenant_id,customer_id,product_id,category_id,ordered_at,status,quantity,unit_price_cents) VALUES(1,1,1,1,'2027-03-01T01:00Z','placed',2,1234) RETURNING id;"))
                    else:
                        sql(f"UPDATE orders SET quantity={quantity},status='{status}' WHERE tenant_id=1 AND id={order_id};")
                    commit_epoch = float(sql(f"SELECT extract(epoch FROM pg_xact_commit_timestamp(xmin)) FROM orders WHERE tenant_id=1 AND id={order_id};"))
                    expected_sales = 0 if status == "cancelled" else quantity * 1234
                    observed = {}
                    response_status = None
                    for _ in range(300):
                        response = client.get("/tenants/1/summary?from=2027-03-01T00:00Z&to=2027-03-02T00:00Z", headers=headers(1))
                        response_status = response.status_code
                        if response_status == 200:
                            observed = response.json().get("data", {})
                        if observed.get("orders") == 1 and observed.get("sales_cents") == expected_sales:
                            break
                        time.sleep(.1)
                    elapsed = time.time() - commit_epoch
                    passed = response_status == 200 and observed.get("orders") == 1 and observed.get("sales_cents") == expected_sales
                    samples.append({"op": operation, "iteration": iteration,
                                    "commit_timestamp_utc": datetime.datetime.fromtimestamp(commit_epoch, datetime.timezone.utc).isoformat(),
                                    "commit_to_response_seconds": elapsed,
                                    "whole_operation_seconds": time.monotonic() - start,
                                    "http_status": response_status, "status": "PASS" if passed else "FAIL"})
            finally:
                if order_id is not None:
                    sql(f"DELETE FROM orders WHERE tenant_id=1 AND id={order_id};")
    after = source_snapshot(query_json)
    artifact = {
        "schema_version": 2, "runner_status": "COMPLETED", "scale": scale, "run": {"run_id": run_id,
            "started_at_utc": started.isoformat(), "finished_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "host": platform.platform(), "machine": platform.machine()},
        "dataset": {"dataset_id": "representative-seed42-v1" if scale == 1_000_000 else None,
                    "official_compatibility": "NOT_VERIFIED"},
        "source_snapshot": before, "source_snapshot_after": after,
        "baseline_cleanup_verified": before == after, "samples": samples,
        "worst_seconds": max((x["commit_to_response_seconds"] for x in samples), default=None),
        "status": "PASS" if len(samples) == 30 and before == after and all(x["status"] == "PASS" and x["commit_to_response_seconds"] < 30 for x in samples) else "FAIL",
        "clock": "PostgreSQL commit timestamp (track_commit_timestamp) to first correct HTTP response; container clocks share the host wall clock.",
    }
    (ROOT / "benchmarks/results" / f"freshness-{scale}.json").write_text(json.dumps(artifact, indent=2))
    print(json.dumps(artifact, indent=2))
    if not artifact["baseline_cleanup_verified"]:
        raise SystemExit("Freshness test did not restore source snapshot")


if __name__ == "__main__":
    main()
