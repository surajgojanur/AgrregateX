import copy
import json
import os
import tempfile
import unittest
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validation import (FAMILIES, RANGES, expected_correctness_coverage,
                        expected_http_coverage, inspect_http_artifact,
                        score_safety)
from growth import compare_artifacts
from acceptance import grade_tests
from run import dataset_metadata


def snapshot(scale):
    tenants = 10 if scale == 1_000_000 else 100
    base = scale // (tenants * 2)
    distribution = [{"tenant_id": tenant, "orders": base} for tenant in range(1, tenants + 1)]
    distribution[0]["orders"] += scale - base * tenants
    return {"order_count": scale, "tenant_count": tenants, "populated_tenant_count": tenants,
            "gross_cents": str(scale * 123), "row_hash_sum": str(scale * 456),
            "tenant_distribution": distribution, "daily_rows": 20, "hourly_rows": 30}


def workload(scale):
    tenants = 10 if scale == 1_000_000 else 100
    return {"ranges": list(RANGES), "range_parameters": {x: [x, x] for x in RANGES},
            "families": [list(x) for x in FAMILIES], "sequential_repeats": 8,
            "concurrent_clients": 4, "concurrent_rounds": 3,
            "api_base_url": "http://localhost:18081", "timezone": "UTC",
            "time_range_semantics": "[from,to)", "top_n_limit": 10,
            "sequential_tenant_roles": {"hot": 1, "second": 2, "small": tenants},
            "concurrent_tenant_roles": {"hot": 1, "second": 2, "middle": 3, "small": tenants}}


def artifact(scale, latency=10):
    source = snapshot(scale)
    requests = []
    for (tenant, family, grain, range_name, mode), count in expected_http_coverage(scale).items():
        requests.extend({"tenant": tenant, "family": family, "grain": grain, "range": range_name,
                         "mode": mode, "http": 200, "ms": latency, "error": None} for _ in range(count))
    correctness = [{"tenant": tenant, "family": family, "grain": grain, "range": range_name, "status": "PASS"}
                   for (tenant, family, grain, range_name), count in expected_correctness_coverage(scale).items()
                   for _ in range(count)]
    return {"schema_version": 2, "runner_status": "COMPLETED", "scale": scale,
            "dataset": {"dataset_id": "official-orders-v1", "generator_id": "official-generator",
                        "generator_version": "1.2.3", "seed": 42,
                        "official_compatibility": "VERIFIED", "manifest_version": 1},
            "run": {"run_id": f"run-{scale}", "started_at_utc": "2026-10-31T00:00:00Z",
                    "finished_at_utc": "2026-10-31T00:01:00Z", "git_commit": "abc123",
                    "postgres_version": "PostgreSQL 18.6"},
            "hardware": {"platform": "Fedora", "machine": "x86_64", "processor": "CPU",
                         "logical_cpus": 4, "ram_bytes": 8_000_000_000},
            "workload": workload(scale), "source_snapshot": source,
            "source_snapshot_after": copy.deepcopy(source), "requests": requests,
            "correctness": correctness,
            "oracle_consistency": {"lock_acquired": True, "lock_mode": "SHARE",
                                   "comparison_count": len(correctness)},
            "rollup_mismatches": [{"name": "daily_product", "mismatches": 0},
                                   {"name": "hourly_category", "mismatches": 0}]}


def safety_artifact(loaded_tx=1.05):
    source = snapshot(1_000_000)
    raw, arms = [], []
    for pair in range(8):
        for loaded in ((False, True) if pair % 2 == 0 else (True, False)):
            kind_counts = {"select": 60, "update": 30, "insert": 30}
            for kind, count in kind_counts.items():
                tx = loaded_tx if loaded else 1.0
                raw.extend({"pair": pair, "dashboard": loaded, "kind": kind,
                            "statement_ms": .1, "commit_ms": .1, "transaction_ms": tx}
                           for _ in range(count))
            arms.append({"pair": pair, "dashboard": loaded, "operations": 120,
                         "dashboard_errors": 0, "operational_actual_rps": 40,
                         "dashboard_actual_rps": 20 if loaded else 0})
    telemetry = []
    phase_events = []
    for arm in arms:
        telemetry.append({"phase": {"pair": arm["pair"], "dashboard": arm["dashboard"], "state": "start"},
                          "postgres": {"wal": {}, "locks_total": 0},
                          "podman": {"containers": [{"name": "agrregatex-postgres-1"}, {"name": "agrregatex-api-1"}]}})
        phase_events.extend({"pair": arm["pair"], "dashboard": arm["dashboard"], "state": state}
                            for state in ("start", "end"))
    return {"schema_version": 2, "runner_status": "COMPLETED", "status": "FAIL",
            "source_snapshot": source, "source_snapshot_after": copy.deepcopy(source),
            "source_cleanup_verified": True,
            "run": {"run_id": "safety-run"}, "dataset": {"dataset_id": "representative-seed42-v1"},
            "pairs": 8, "operations_per_arm": 960, "operations_per_pair_arm": 120,
            "dashboard_rps_target": 20, "operational_rps_target": 40,
            "arms": arms, "samples": raw, "telemetry": telemetry,
            "phase_events": phase_events, "telemetry_errors": []}


class ValidationTests(unittest.TestCase):
    def test_loader_manifest_adapter_preserves_provenance_fields(self):
        manifest = {"manifest_version": 1, "official_dataset_compatibility": "NOT VERIFIED",
                    "run_id": "load-1", "state": "active", "generator": "representative-v1",
                    "generator_version": "1.0", "seed": 42, "source_rows": 1_000_000,
                    "tenant_count": 10, "tenant_distribution": []}
        old = os.environ.get("AGRREGATEX_DATASET_MANIFEST")
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as f:
            json.dump(manifest, f)
            f.flush()
            os.environ["AGRREGATEX_DATASET_MANIFEST"] = f.name
            try:
                metadata = dataset_metadata(1_000_000)
            finally:
                if old is None:
                    os.environ.pop("AGRREGATEX_DATASET_MANIFEST", None)
                else:
                    os.environ["AGRREGATEX_DATASET_MANIFEST"] = old
        self.assertEqual(metadata["generator_id"], "representative-v1")
        self.assertEqual(metadata["official_compatibility"], "NOT VERIFIED")
        self.assertEqual(metadata["loader_run_id"], "load-1")
        self.assertEqual(metadata["loader_manifest"], manifest)

    def test_functional_grading_rejects_missing_and_duplicate_cases(self):
        baseline = snapshot(1_000_000)
        clean = {"schema_version": 2, "baseline_cleanup_verified": True,
                 "source_snapshot": baseline, "source_snapshot_after": copy.deepcopy(baseline),
                 "tests": [{"name": "case-a", "status": "PASS"}]}
        self.assertEqual(grade_tests(clean, baseline, {"case-a": 1}), "PASS")
        self.assertEqual(grade_tests(clean, baseline, {"case-a": 2}), "NOT TESTED")
        duplicated = copy.deepcopy(clean)
        duplicated["tests"].append({"name": "case-a", "status": "PASS"})
        self.assertEqual(grade_tests(duplicated, baseline, {"case-a": 1}), "NOT TESTED")

    def test_complete_http_coverage_is_valid_at_both_scales(self):
        for scale in (1_000_000, 10_000_000):
            self.assertFalse(any(inspect_http_artifact(artifact(scale), scale).values()))

    def test_missing_http_case_is_incomplete(self):
        result = artifact(1_000_000)
        result["requests"].pop()
        self.assertTrue(inspect_http_artifact(result, 1_000_000)["request_coverage"])

    def test_http_error_is_measured_failure(self):
        result = artifact(1_000_000)
        result["requests"][0]["http"] = 503
        self.assertTrue(inspect_http_artifact(result, 1_000_000)["request_failures"])

    def test_missing_oracle_and_rollup_are_rejected(self):
        result = artifact(1_000_000)
        result["correctness"].pop()
        result["rollup_mismatches"] = [{"name": "daily_product", "mismatches": 0}]
        inspected = inspect_http_artifact(result, 1_000_000)
        self.assertTrue(inspected["oracle_coverage"])
        self.assertTrue(inspected["rollup_coverage"])

    def test_growth_requires_full_matched_official_artifacts(self):
        one, ten = artifact(1_000_000), artifact(10_000_000)
        self.assertEqual(compare_artifacts(one, ten)["status"], "PASS")
        ten["requests"].pop()
        self.assertEqual(compare_artifacts(one, ten)["status"], "NOT TESTED")

    def test_growth_fails_measured_latency_ratio_and_rejects_http_failures(self):
        one, ten = artifact(1_000_000, latency=10), artifact(10_000_000, latency=25)
        self.assertEqual(compare_artifacts(one, ten)["status"], "FAIL")
        one, ten = artifact(1_000_000), artifact(10_000_000)
        ten["requests"][0]["http"] = 500
        self.assertEqual(compare_artifacts(one, ten)["status"], "NOT TESTED")

    def test_growth_requires_same_hardware_dataset_and_workload(self):
        one, ten = artifact(1_000_000), artifact(10_000_000)
        ten["hardware"]["machine"] = "arm64"
        self.assertEqual(compare_artifacts(one, ten)["status"], "NOT TESTED")
        ten = artifact(10_000_000)
        ten["hardware"]["ram_bytes"] += 1
        self.assertEqual(compare_artifacts(one, ten)["status"], "NOT TESTED")
        ten = artifact(10_000_000)
        ten["run"]["postgres_version"] = "PostgreSQL 18.7"
        self.assertEqual(compare_artifacts(one, ten)["status"], "NOT TESTED")
        ten = artifact(10_000_000)
        ten["dataset"]["official_compatibility"] = "NOT_VERIFIED"
        self.assertEqual(compare_artifacts(one, ten)["status"], "NOT TESTED")

    def test_safety_is_scored_from_raw_samples_not_claimed_status(self):
        status, errors, metrics = score_safety(safety_artifact(1.05))
        self.assertEqual(status, "PASS")
        self.assertFalse(errors)
        self.assertLess(metrics["all"]["transaction_ms"]["mean_slowdown_percent"], 10)
        self.assertEqual(len(metrics["paired"]["all"]["pairs"]), 8)
        status, _, _ = score_safety(safety_artifact(1.2))
        self.assertEqual(status, "FAIL")

    def test_safety_missing_samples_or_telemetry_cannot_pass(self):
        result = safety_artifact()
        result["samples"].pop()
        self.assertEqual(score_safety(result)[0], "NOT TESTED")
        result = safety_artifact()
        result["telemetry"] = []
        self.assertEqual(score_safety(result)[0], "NOT TESTED")


if __name__ == "__main__":
    unittest.main()
