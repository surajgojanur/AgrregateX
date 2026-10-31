#!/usr/bin/env python3
"""Bounded, fail-closed PRD acceptance runner for the preserved 1M database."""
import datetime
import json
import os
import platform
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from db import ROOT, query_json
from validation import (FAMILIES, RANGES, inspect_http_artifact, source_snapshot,
                        score_safety, validate_freshness, validate_functional,
                        validate_http_artifact, validate_security)

RESULTS = ROOT / "benchmarks/results"
RUN_ID = uuid.uuid4().hex


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2))
    os.replace(temporary, path)


def test_map(artifact):
    result = {}
    for item in artifact.get("tests", []) if isinstance(artifact, dict) else []:
        result.setdefault(item.get("name"), []).append(item)
    return result


def grade_tests(artifact, before, required):
    if not artifact or artifact.get("schema_version") != 2 or artifact.get("baseline_cleanup_verified") is not True or artifact.get("source_snapshot") != before or artifact.get("source_snapshot_after") != before:
        return "NOT TESTED"
    records = test_map(artifact)
    missing = [name for name, count in required.items() if len(records.get(name, [])) != count]
    if missing:
        return "NOT TESTED"
    selected = [item for name, count in required.items() for item in records[name][:count]]
    return "PASS" if all(item.get("status") == "PASS" for item in selected) else "FAIL"


def build_functional_requirements(artifacts, before, populated_tenants):
    fr = {f"FR-{n}": "NOT TESTED" for n in range(1, 8)}
    func = artifacts.get("functional", {})
    if func:
        metadata_errors = validate_functional(func, before)
        # A failed assertion is evidence of FAIL; malformed/missing case IDs are NOT TESTED.
        for n, family in ((1, "summary"), (2, "trends"), (3, "top-products"), (4, "breakdown")):
            required = {}
            for tenant in (1, 2):
                for ri in range(4):
                    grains = ("day", "hour") if family == "trends" else ("day",)
                    for grain in grains:
                        name = f"fixture-{ri}:{tenant}:{family}:{grain}"
                        required[name] = 1
                        required[name + ":oracle"] = 1
            for mutation in range(4):
                grains = ("day", "hour") if family == "trends" else ("day",)
                for grain in grains:
                    name = f"mutation{mutation}:1:{family}:{grain}"
                    required[name] = 1
                    required[name + ":oracle"] = 1
            if family == "top-products":
                required.update({"top-products-tie": 1, "top-products-tie:oracle": 1})
            # Only a failed required assertion should be graded FAIL. Missing
            # coverage or invalid artifact metadata is explicitly NOT TESTED.
            records = test_map(func)
            absent = any(len(records.get(name, [])) != count for name, count in required.items())
            if absent or metadata_errors:
                fr[f"FR-{n}"] = "NOT TESTED"
            else:
                fr[f"FR-{n}"] = grade_tests(func, before, required)

        required_mutations = {
            "create1": 1, "create2": 1, "duplicate-create": 1, "conflicting-event": 1,
            **{f"patch{i}": 1 for i in range(4)},
            **{f"replayed-update{i}": 1 for i in range(4)},
            "concurrent-duplicate": 1, "failed-transaction-atomic": 1,
            "delete-test-record": 6,
        }
        records = test_map(func)
        if any(len(records.get(name, [])) != count for name, count in required_mutations.items()) or metadata_errors:
            fr["FR-6"] = "NOT TESTED"
        else:
            fr["FR-6"] = grade_tests(func, before, required_mutations)

        required_api = {"health": 1, "dashboard": 1, "openapi-json": 1, "swagger-docs": 1}
        http = artifacts.get("http", {})
        http_check = inspect_http_artifact(http, 1_000_000) if http else None
        if any(len(records.get(name, [])) != count for name, count in required_api.items()) or metadata_errors or not http_check or http_check["metadata"] or http_check["request_coverage"]:
            fr["FR-7"] = "NOT TESTED"
        elif any(len(records.get(name, [])) != count for name, count in required_api.items()):
            fr["FR-7"] = "NOT TESTED"
        elif any(records[name][0].get("status") != "PASS" for name in required_api) or http_check["request_failures"]:
            fr["FR-7"] = "FAIL"
        else:
            fr["FR-7"] = grade_tests(func, before, required_api)

    security = artifacts.get("security", {})
    security_errors = validate_security(security, populated_tenants)
    if security:
        if not security_errors:
            fr["FR-5"] = "PASS (10 populated tenants; 100 API identities tested)"
        else:
            tenant_rows = security.get("tenants") if isinstance(security.get("tenants"), list) else []
            test_rows = security.get("tests") if isinstance(security.get("tests"), list) else []
            measured_failure = (any(isinstance(x, dict) and x.get("status") == "FAIL" for x in tenant_rows) or
                                any(isinstance(x, dict) and x.get("status") == "FAIL" for x in test_rows))
            incomplete = any(token in " ".join(security_errors).lower() for token in
                             ("incomplete", "missing", "matrix does not cover", "not verified", "expects exactly"))
            fr["FR-5"] = "FAIL" if measured_failure or security.get("baseline_cleanup_verified") is False else "NOT TESTED" if incomplete else "FAIL"
    return fr


def run_bounded():
    jobs = [
        ("functional", ["python3", "benchmarks/functional.py"], "functional.json", 180),
        ("http", ["python3", "benchmarks/run.py", "1000000"], "benchmark-1000000.json", 240),
        ("freshness", ["python3", "benchmarks/freshness.py", "1000000"], "freshness-1000000.json", 180),
        ("safety", ["python3", "benchmarks/safety.py", "1000000"], "safety-1000000.json", 900),
        ("security", ["python3", "benchmarks/security.py"], "security.json", 240),
    ]
    steps = []
    artifacts = {}
    before = after = None
    errors = []
    try:
        before = source_snapshot(query_json)
        if before["order_count"] != 1_000_000 or before["tenant_count"] != 10:
            errors.append(f"baseline is not 1M/10: {before.get('order_count')}/{before.get('tenant_count')}")
            return before, None, steps, artifacts, errors
        for name, command, artifact_name, timeout in jobs:
            path = RESULTS / artifact_name
            old_mtime = path.stat().st_mtime_ns if path.exists() else 0
            started = time.monotonic()
            try:
                proc = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=timeout)
                stdout, stderr, exit_code = proc.stdout or "", proc.stderr or "", proc.returncode
                timed_out = False
            except subprocess.TimeoutExpired as exc:
                stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
                stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
                exit_code = None
                timed_out = True
                errors.append(f"{name} timed out after {timeout}s")
            except Exception as exc:
                stdout, stderr, exit_code, timed_out = "", repr(exc), None, False
                errors.append(f"{name} could not run: {type(exc).__name__}: {exc}")
            write_json(RESULTS / f"acceptance-{name}-execution.json", {"run_id": RUN_ID, "command": command,
                       "exit_code": exit_code, "timed_out": timed_out, "stdout": stdout, "stderr": stderr})
            fresh_artifact = path.exists() and path.stat().st_mtime_ns > old_mtime
            step = {"name": name, "command": command, "exit_code": exit_code,
                    "timed_out": timed_out, "seconds": round(time.monotonic() - started, 3),
                    "artifact_written_this_run": fresh_artifact}
            steps.append(step)
            if not fresh_artifact:
                errors.append(f"{name} did not produce a current-run artifact")
                break
            try:
                artifacts[name] = json.loads(path.read_text())
            except Exception as exc:
                errors.append(f"{name} artifact could not be parsed: {type(exc).__name__}")
                break
            step["artifact_parsed"] = True
            if exit_code != 0:
                step["test_process_nonzero"] = True
                if artifacts[name].get("runner_status") != "COMPLETED":
                    errors.append(f"{name} test process failed before completing its evidence: {stderr[-500:]}")
    except Exception as exc:
        errors.append(f"acceptance setup failed: {type(exc).__name__}: {exc}")
    finally:
        try:
            after = source_snapshot(query_json)
        except Exception as exc:
            errors.append(f"final baseline snapshot failed: {type(exc).__name__}: {exc}")
    return before, after, steps, artifacts, errors


def score(before, after, steps, artifacts, runner_errors, growth_result):
    baseline_ok = before is not None and after is not None and before == after
    if before is not None and after is not None and not baseline_ok:
        runner_errors = [*runner_errors, "source/rollup baseline changed during bounded acceptance"]
    fr = build_functional_requirements(artifacts, before, before.get("populated_tenant_count", 0) if before else 0)

    http = artifacts.get("http", {})
    http_inspection = inspect_http_artifact(http, 1_000_000) if http else None
    http_errors = validate_http_artifact(http, 1_000_000) if http else ["missing HTTP artifact"]
    if not http_inspection or any(http_inspection[k] for k in ("metadata", "request_coverage")):
        g1 = "NOT TESTED"
    elif http_inspection["request_failures"] or any(x["ms"] >= 200 for x in http.get("requests", [])):
        g1 = "FAIL"
    else:
        g1 = "PASS (1M representative dataset only)"

    freshness = artifacts.get("freshness", {})
    freshness_errors = validate_freshness(freshness, 1_000_000) if freshness else ["missing freshness artifact"]
    incomplete_freshness = any(token in " ".join(freshness_errors).lower() for token in
                               ("missing", "incomplete", "metadata", "coverage", "requires exactly"))
    g2 = "NOT TESTED" if incomplete_freshness else "FAIL" if freshness_errors else "PASS (1M representative dataset only)"

    safety = artifacts.get("safety", {})
    g3, safety_errors, safety_metrics = score_safety(safety)
    if g3 == "PASS":
        g3 = "PASS (bounded mixed OLTP workload only)"

    if not http_inspection or any(http_inspection[k] for k in ("metadata", "oracle_coverage", "consistency", "rollup_coverage")):
        g4 = "NOT TESTED"
    elif any(http_inspection[k] for k in ("oracle_failures", "rollup_failures")):
        g4 = "FAIL"
    else:
        g4 = "PASS (1M measured scopes)"
    g5 = growth_result.get("status", "NOT TESTED") if isinstance(growth_result, dict) else "NOT TESTED"

    fr = {k: (v if baseline_ok else "NOT TESTED") for k, v in fr.items()}
    great = {"G-1": g1, "G-2": g2, "G-3": g3, "G-4": g4, "G-5": g5}
    if not baseline_ok:
        great = {k: "NOT TESTED" for k in great}
    results = list(fr.values()) + list(great.values())
    if any(x.startswith("FAIL") for x in results):
        prd_status = "FAIL"
    elif any(x.startswith("NOT TESTED") for x in results) or not before or not before.get("official_dataset_verified", False):
        prd_status = "NOT VERIFIED"
    else:
        prd_status = "PASS"
    runner_status = "COMPLETED" if not runner_errors and len(steps) == 5 and all(x.get("artifact_parsed") for x in steps) and baseline_ok else "FAILED"
    report = {
        "schema_version": 2, "run_id": RUN_ID,
        "captured_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "runner_status": runner_status, "runner_errors": runner_errors,
        "prd_status": prd_status,
        "dataset": {"dataset_id": artifacts.get("http", {}).get("dataset", {}).get("dataset_id"),
                    "official_compatibility": "NOT VERIFIED", "scale": "1,000,000 orders / 10 tenants"},
        "source_snapshot_before": before, "source_snapshot_after": after,
        "baseline_cleanup_verified": baseline_ok,
        "functional_requirements": fr, "great_targets": great,
        "http_requests": len(http.get("requests", [])),
        "http_successes": sum(r.get("http") == 200 for r in http.get("requests", [])),
        "http_failures": sum(r.get("http") != 200 for r in http.get("requests", [])),
        "http_latency_by_query_family": http.get("latency", {}),
        "http_coverage_errors": http_errors,
        "correctness_comparisons": len(http.get("correctness", [])),
        "correctness_failures": sum(x.get("status") != "PASS" for x in http.get("correctness", [])),
        "rollup_mismatch_rows": http.get("rollup_mismatches", []),
        "freshness_samples": len(freshness.get("samples", [])),
        "freshness_errors": freshness_errors,
        "freshness_worst_seconds": freshness.get("worst_seconds"),
        "safety_status": safety.get("status", "NOT TESTED"),
        "safety_method": {k: safety.get(k) for k in ("pairs", "operations_per_arm", "dashboard_rps_target", "operational_rps_target")},
        "safety_metrics": safety_metrics, "safety_errors": safety_errors,
        "safety_telemetry_samples": len(safety.get("telemetry", [])),
        "security_identities": len(artifacts.get("security", {}).get("tenants", [])),
        "steps": steps, "host": {"platform": platform.platform(), "machine": platform.machine()},
    }
    return report


def main():
    if sys.argv[1:] != ["--bounded"]:
        raise SystemExit("Usage: python3 benchmarks/acceptance.py --bounded")
    RESULTS.mkdir(parents=True, exist_ok=True)
    initial = {"schema_version": 2, "run_id": RUN_ID, "runner_status": "RUNNING", "prd_status": "NOT VERIFIED",
               "functional_requirements": {f"FR-{i}": "NOT TESTED" for i in range(1, 8)},
               "great_targets": {f"G-{i}": "NOT TESTED" for i in range(1, 6)}}
    write_json(RESULTS / "acceptance.json", initial)
    before, after, steps, artifacts, errors = run_bounded()
    # growth.py is a scoring-only operation; it uses current scale evidence and
    # never starts a loader. Run even after partial acceptance so G-5 is explicit.
    growth_result = None
    growth_path = RESULTS / "growth.json"
    previous_growth_mtime = growth_path.stat().st_mtime_ns if growth_path.exists() else 0
    try:
        p = subprocess.run(["python3", "benchmarks/growth.py"], cwd=ROOT, text=True, capture_output=True, timeout=30)
        if p.returncode:
            errors.append("growth scorer failed: " + (p.stderr[-500:] if p.stderr else "unknown error"))
        else:
            try:
                growth = json.loads(growth_path.read_text())
                # If no 10M data is present, this is the expected current result.
                if growth.get("status") not in ("PASS", "FAIL", "NOT TESTED"):
                    errors.append("growth scorer returned an invalid status")
                elif growth_path.stat().st_mtime_ns > previous_growth_mtime:
                    growth_result = growth
            except Exception as exc:
                errors.append(f"growth result unavailable: {type(exc).__name__}")
    except Exception as exc:
        errors.append(f"growth scorer could not run: {type(exc).__name__}")
    try:
        report = score(before, after, steps, artifacts, errors, growth_result)
    except Exception as exc:
        report = {"schema_version": 2, "run_id": RUN_ID, "runner_status": "FAILED",
                  "prd_status": "NOT VERIFIED", "runner_errors": [*errors, f"scoring failed safely: {type(exc).__name__}: {exc}"],
                  "baseline_cleanup_verified": before is not None and after is not None and before == after,
                  "functional_requirements": {f"FR-{i}": "NOT TESTED" for i in range(1, 8)},
                  "great_targets": {f"G-{i}": "NOT TESTED" for i in range(1, 6)}}
    write_json(RESULTS / "acceptance.json", report)
    print(json.dumps(report, indent=2))
    # Exit status describes harness/cleanup execution. PRD measurement failures
    # remain in prd_status and never get converted into runner success claims.
    return 0 if report["runner_status"] == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
