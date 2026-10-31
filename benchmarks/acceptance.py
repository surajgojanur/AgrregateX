#!/usr/bin/env python3
"""Run the bounded PRD suite against the existing 1M AgrregateX database."""
import datetime
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from db import ROOT, query_json

RESULTS = ROOT / "benchmarks/results"


def snapshot():
    return query_json(
        "SELECT (SELECT count(*) FROM orders) order_count, "
        "(SELECT count(*) FROM tenants) tenant_count, "
        "(SELECT coalesce(sum(quantity::bigint * unit_price_cents),0) FROM orders) gross_cents, "
        "(SELECT count(*) FROM daily_product) daily_rows, "
        "(SELECT count(*) FROM hourly_category) hourly_rows"
    )[0]


def main():
    if sys.argv[1:] != ["--bounded"]:
        raise SystemExit("Usage: python3 benchmarks/acceptance.py --bounded")

    before = snapshot()
    if before["order_count"] != 1_000_000:
        raise SystemExit(f"Expected preserved 1M baseline, found {before['order_count']}; refusing to proceed.")

    # Each component is bounded and owns its own fixtures. Deliberately omit the
    # separate reliability script because it stops/restarts live containers.
    jobs = [
        ("functional", ["python3", "benchmarks/functional.py"], "functional.json"),
        ("http", ["python3", "benchmarks/run.py", "1000000"], "benchmark-1000000.json"),
        ("freshness", ["python3", "benchmarks/freshness.py", "1000000"], "freshness-1000000.json"),
        ("safety", ["python3", "benchmarks/safety.py", "1000000"], "safety-1000000.json"),
        ("security", ["python3", "benchmarks/security.py"], "security.json"),
    ]
    steps = []
    start = time.monotonic()
    for name, command, artifact in jobs:
        path = RESULTS / artifact
        old_mtime = path.stat().st_mtime_ns if path.exists() else 0
        then = time.monotonic()
        p = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=900)
        (RESULTS / f"acceptance-{name}-stdout.log").write_text(p.stdout)
        (RESULTS / f"acceptance-{name}-stderr.log").write_text(p.stderr)
        fresh_artifact = path.exists() and path.stat().st_mtime_ns > old_mtime
        steps.append({"name": name, "command": command, "exit_code": p.returncode,
                      "seconds": round(time.monotonic() - then, 3),
                      "artifact_written_this_run": fresh_artifact})
        if p.returncode or not fresh_artifact:
            break

    after = snapshot()
    cleanup_ok = before == after
    artifacts = {}
    for name, _, artifact in jobs:
        path = RESULTS / artifact
        step = next((x for x in steps if x["name"] == name), None)
        if step and step["exit_code"] == 0 and step["artifact_written_this_run"]:
            try:
                artifacts[name] = json.loads(path.read_text())
            except Exception:
                artifacts[name] = {}

    functional = artifacts.get("functional", {}).get("tests", [])
    http = artifacts.get("http", {})
    fresh = artifacts.get("freshness", {}).get("samples", [])
    safety = artifacts.get("safety", {})
    security = artifacts.get("security", {})
    fr = {f"FR-{i}": "NOT TESTED" for i in range(1, 8)}
    names = [x.get("name", "") for x in functional]

    def passing_prefix(prefixes):
        selected = [x for x in functional if any(x.get("name", "").startswith(p) for p in prefixes)]
        return bool(selected) and all(x.get("status") == "PASS" for x in selected)

    fr["FR-1"] = "PASS (1M bounded fixtures)" if passing_prefix(["fixture:", "mutation"]) else "NOT TESTED"
    fr["FR-2"] = "PASS (1M bounded fixtures)" if any("trends" in n for n in names) and passing_prefix(["fixture:", "mutation"]) else "NOT TESTED"
    fr["FR-3"] = "PASS (1M bounded fixtures)" if passing_prefix(["fixture:", "mutation"]) and any("top-products" in n for n in names) else "NOT TESTED"
    fr["FR-4"] = "PASS (1M bounded fixtures)" if passing_prefix(["fixture:", "mutation"]) and any("breakdown" in n for n in names) else "NOT TESTED"
    fr["FR-5"] = "PASS (100 API identities)" if security.get("status") == "PASS" and len(security.get("tenants", [])) == 100 else "FAIL" if security.get("status") == "FAIL" else "NOT TESTED"
    mutation_names = [n for n in names if n.startswith(("create", "patch", "replayed-update", "delete-test-record", "concurrent-duplicate"))]
    mutation_ok = any(n == "patch0" for n in names) and any(n == "patch1" for n in names) and any(n.startswith("replayed-update") for n in names)
    fr["FR-6"] = "PASS (bounded insert/update/cancel/delete/replay)" if mutation_ok and mutation_names and passing_prefix(["create", "patch", "replayed-update", "delete-test-record", "concurrent-duplicate"]) else "NOT TESTED"
    fr["FR-7"] = "PASS (API/OpenAPI smoke)" if passing_prefix(["openapi"]) and http.get("errors") == 0 else "NOT TESTED"

    requests = http.get("requests", [])
    http_ok = [r for r in requests if r.get("http") == 200]
    max_http = max((r.get("ms", 0) for r in http_ok), default=None)
    correctness = http.get("correctness", [])
    rollups = http.get("rollup_mismatches", [])
    complete = bool(requests) and all(r.get("http") == 200 for r in requests)
    great = {
        "G-1": ("PASS at 1M only" if complete and max_http is not None and max_http < 200 else "FAIL at 1M" if requests else "NOT TESTED"),
        "G-2": ("PASS at 1M only" if fresh and all(x.get("status") == "PASS" and x.get("commit_to_response_seconds", 999) < 30 for x in fresh) else "FAIL at 1M" if fresh else "NOT TESTED"),
        "G-3": ("PASS narrow 1M experiment only" if safety.get("status") == "PASS" and len(safety.get("samples", [])) >= 1000 else "FAIL" if safety.get("status") == "FAIL" else "NOT TESTED"),
        "G-4": ("PASS for measured 1M scopes" if correctness and all(x.get("status") == "PASS" for x in correctness) and rollups and all(x.get("mismatches") == 0 for x in rollups) else "FAIL" if any(x.get("status") == "FAIL" for x in correctness) or any(x.get("mismatches", 0) for x in rollups) else "NOT TESTED"),
        "G-5": "NOT TESTED — no 10M run permitted in this phase",
    }
    report = {
        "application": "AgrregateX", "captured_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "dataset": "representative seed42; official generator compatibility NOT VERIFIED",
        "scale": "1,000,000 orders / 10 tenants", "source_snapshot_before": before,
        "source_snapshot_after": after, "baseline_cleanup_verified": cleanup_ok,
        "functional_requirements": fr, "great_targets": great,
        "http_requests": len(requests), "http_successes": len(http_ok),
        "http_failures": len(requests) - len(http_ok), "max_successful_http_ms": max_http,
        "http_latency_by_query_family": http.get("latency", {}),
        "correctness_comparisons": len(correctness),
        "correctness_failures": sum(x.get("status") == "FAIL" for x in correctness),
        "rollup_mismatch_rows": rollups, "freshness_samples": len(fresh),
        "freshness_worst_seconds": artifacts.get("freshness", {}).get("worst_seconds"),
        "safety_status": safety.get("status", "NOT TESTED"),
        "safety_method": {k: safety.get(k) for k in ["dashboard_rps_target", "dashboard_clients", "operational_rps_target", "pairs", "operations_per_arm"]},
        "safety_metrics": safety.get("metrics", {}),
        "security_tenants": len(security.get("tenants", [])),
        "steps": steps, "duration_seconds": round(time.monotonic() - start, 3),
        "host": {"platform": platform.platform(), "machine": platform.machine()},
        "overall": "PARTIAL — official dataset and 10M targets not tested",
    }
    (RESULTS / "acceptance.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if not cleanup_ok or any(x["exit_code"] != 0 for x in steps):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
