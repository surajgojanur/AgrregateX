"""Adversarial parser tests use fabricated validator fixtures, never benchmark claims."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from verify_scale_evidence import EXPECTED, audit


def _write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=True), encoding="utf-8")


def fixture_tree(root: Path):
    results = root / "results"
    roles = {
        "1m": {"largest": [1, 340560], "median": [6, 56965], "smallest": [10, 34091]},
        "10m": {"largest": [1, 1930247], "median": [51, 37901], "smallest": [100, 19471]},
    }
    all_rows = {}
    for label in ("1m", "10m"):
        rows = []
        for endpoint, role, window in sorted(EXPECTED):
            tenant_id, tenant_orders = roles[label][role]
            rows.append({"endpoint": endpoint, "tenant_role": role, "window": window,
                         "tenant_id": tenant_id, "tenant_orders": tenant_orders,
                         "n": 50, "status_counts": {"200": 50}, "errors": 0,
                         "p50": 4.0, "p95": 4.0 if label == "1m" else 6.0,
                         "p99": 5.0 if label == "1m" else 7.0,
                         "max": 5.0 if label == "1m" else 7.0,
                         "mean": 4.5 if label == "1m" else 6.5})
        all_rows[label] = rows
        summary = {"orders_total": 1_000_000 if label == "1m" else 10_000_000,
                   "tenants": 10 if label == "1m" else 100, "roles": roles[label],
                   "scenarios": 72, "requests": 3600, "errors": 0,
                   "worst_p95_ms": 4.0 if label == "1m" else 6.0,
                   "scenarios_p95_under_200ms": 72, "scenarios_p95_under_1000ms": 72}
        folder = "1m-10t-http" if label == "1m" else "10m-100t-http"
        _write(results / folder / "summary.json", summary)
        _write(results / folder / "scenarios.json", rows)

    ratios = [{"endpoint": row["endpoint"], "role": row["tenant_role"], "window": row["window"],
               "p95_1m": 4.0, "p95_10m": 6.0, "ratio": 1.5} for row in all_rows["1m"]]
    _write(results / "10m-100t-http" / "growth_vs_1m.json",
           {"median": 1.5, "min": 1.5, "max": 1.5, "n": 72, "under_2x": 72, "under_5x": 72, "ratios": ratios})
    tenants = [{"tenant_id": i, "orders": 1} for i in range(1, 101)]
    snapshot = {"captured_at": "2026-11-01T00:00:00Z", "version": "PostgreSQL 18.6",
                "pg_trickle": "0.108.3", "total_orders": 10_000_000,
                "generated_orders": 10_000_000, "distinct_ids": 10_000_000,
                "gen_params": {"orders": 10_000_000, "tenants": 100, "seed": 42},
                "tenants": tenants, "stream_tables": [{"name": table} for table in sorted({
                    "st_day_product_status", "st_day_category_status", "st_hour_category_status"})]}
    _write(results / "10m-100t-proof" / "db-snapshot.json", snapshot)
    _write(results / "10m-100t-proof" / "api-vs-db-100-tenants.json",
           {"all_match": True, "mismatches": [], "rows": [{} for _ in range(100)],
            "api_total": 10_000_000, "db_total": 10_000_000})
    (results / "10m-100t-proof" / "oracle-lowmem.txt").write_text(
        "st_day_product_status|0|0\nst_day_category_status|0|0\nst_hour_category_status|0|0\n", encoding="utf-8")
    (results / "REPORT-10m.md").write_text("representative", encoding="utf-8")
    return results


class EvidenceAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.results = fixture_tree(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def _audit(self):
        return audit(self.root, "fixture-only")

    def test_fixture_arithmetic_passes_but_official_pass_never_does(self):
        result = self._audit()
        self.assertFalse(result["official_pass"])
        self.assertEqual(result["classifications"]["growth_arithmetic"], "VALIDATED FROM ARTIFACT")
        self.assertEqual(result["g5"]["matched_scenarios"], 72)

    def test_missing_scenario_is_failed(self):
        path = self.results / "10m-100t-http/scenarios.json"
        rows = json.loads(path.read_text())
        _write(path, rows[:-1])
        result = self._audit()
        self.assertEqual(result["classifications"]["10m_scenario_artifact_consistency"], "FAILED")

    def test_duplicate_scenario_is_failed(self):
        path = self.results / "10m-100t-http/scenarios.json"
        rows = json.loads(path.read_text())
        rows[-1] = copy.deepcopy(rows[0])
        _write(path, rows)
        self.assertEqual(self._audit()["classifications"]["10m_scenario_artifact_consistency"], "FAILED")

    def test_invalid_sample_size_is_failed(self):
        path = self.results / "10m-100t-http/scenarios.json"
        rows = json.loads(path.read_text()); rows[0]["n"] = 49; _write(path, rows)
        self.assertEqual(self._audit()["classifications"]["10m_scenario_artifact_consistency"], "FAILED")

    def test_missing_error_counter_is_failed(self):
        path = self.results / "10m-100t-http/scenarios.json"
        rows = json.loads(path.read_text()); rows[0].pop("errors"); _write(path, rows)
        self.assertEqual(self._audit()["classifications"]["10m_scenario_artifact_consistency"], "FAILED")

    def test_nan_latency_is_failed(self):
        path = self.results / "10m-100t-http/scenarios.json"
        rows = json.loads(path.read_text()); rows[0]["p95"] = float("nan"); _write(path, rows)
        self.assertEqual(self._audit()["classifications"]["10m_scenario_artifact_consistency"], "FAILED")

    def test_negative_latency_is_failed(self):
        path = self.results / "10m-100t-http/scenarios.json"
        rows = json.loads(path.read_text()); rows[0]["p50"] = -1; _write(path, rows)
        self.assertEqual(self._audit()["classifications"]["10m_scenario_artifact_consistency"], "FAILED")

    def test_contradictory_summary_totals_are_failed(self):
        path = self.results / "10m-100t-http/summary.json"
        summary = json.loads(path.read_text()); summary["requests"] = 3599; _write(path, summary)
        self.assertEqual(self._audit()["classifications"]["10m_scenario_artifact_consistency"], "FAILED")

    def test_wrong_percentile_order_is_failed(self):
        path = self.results / "10m-100t-http/scenarios.json"
        rows = json.loads(path.read_text()); rows[0]["p95"] = 3; _write(path, rows)
        self.assertEqual(self._audit()["classifications"]["10m_scenario_artifact_consistency"], "FAILED")

    def test_corrupted_json_and_missing_artifact_fail_closed(self):
        path = self.results / "10m-100t-http/scenarios.json"
        path.write_text("{bad json", encoding="utf-8")
        self.assertEqual(self._audit()["classifications"]["artifact_parse"], "FAILED")
        path.unlink()
        self.assertEqual(self._audit()["classifications"]["artifact_parse"], "FAILED")

    def test_wrong_growth_pairs_are_failed(self):
        path = self.results / "10m-100t-http/growth_vs_1m.json"
        growth = json.loads(path.read_text()); growth["ratios"].pop(); _write(path, growth)
        self.assertEqual(self._audit()["classifications"]["growth_arithmetic"], "FAILED")

    def test_source_provenance_and_post_mutation_g4_are_not_promoted(self):
        result = self._audit()
        self.assertEqual(result["classifications"]["matched_run_provenance"], "INSUFFICIENT EVIDENCE")
        self.assertIn("NOT TESTED", result["g4"]["post_mutation_correctness"])

    def test_acceptance_scorecard_distinguishes_artifact_math_from_missing_runtime_proof(self):
        result = self._audit()
        self.assertEqual(result["classifications"]["g1_threshold_arithmetic"], "VALIDATED FROM ARTIFACT")
        self.assertEqual(result["classifications"]["g1_percentile_source"], "REPORTED BUT NOT INDEPENDENTLY RECOMPUTABLE")
        self.assertEqual(result["classifications"]["g1_official_qualification"], "INSUFFICIENT EVIDENCE")
        self.assertEqual(result["classifications"]["g2_10m_freshness"], "NOT TESTED")
        self.assertEqual(result["classifications"]["g3_10m_write_safety"], "NOT TESTED")
        self.assertEqual(result["classifications"]["g4_10m_post_mutation"], "NOT TESTED")
        self.assertEqual(result["classifications"]["g5_official_qualification"], "INSUFFICIENT EVIDENCE")

    def test_missing_scale_metadata_is_not_a_pass(self):
        path = self.results / "10m-100t-proof/db-snapshot.json"
        snap = json.loads(path.read_text()); snap["gen_params"].pop("seed"); _write(path, snap)
        self.assertEqual(self._audit()["classifications"]["10m_dataset_snapshot_consistency"], "FAILED")

    def test_unexpected_dataset_types_are_failed(self):
        path = self.results / "10m-100t-proof/db-snapshot.json"
        snap = json.loads(path.read_text()); snap["tenants"] = "one hundred"; _write(path, snap)
        self.assertEqual(self._audit()["classifications"]["10m_dataset_snapshot_consistency"], "FAILED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
