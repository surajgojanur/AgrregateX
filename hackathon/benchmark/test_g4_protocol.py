"""Offline policy tests; these do not claim PostgreSQL runtime coverage."""

import unittest
import re
from pathlib import Path

from hackathon.benchmark.g4_protocol import classify_evidence, experiment_config, validate_sql_safety

PREP = Path(__file__).parent / "results/issue31/20261101T2137Z-controlled-prep"


def complete_evidence():
    negative = {"change_id": 2, "action": "D", "order_id": 7}
    return {
        "runtime_executed": True,
        "before_frontier": "0/10",
        "after_frontier": "0/20",
        "frontiers_correlate": True,
        "refresh_history": {
            "action": "DIFFERENTIAL",
            "status": "COMPLETED",
            "was_full_fallback": False,
        },
        "raw_cdc": [negative],
        "stage_before_compaction": [negative],
        "stage_after_compaction": [],
        "stage_after_visibility": [],
        "producer_observed": "p5_direct_sql",
        "aggregate_delta_observed": [{"status": "paid", "delta": 1}],
        "apply_observed": "agg_fast_path",
        "oracle_results": [{"table": "st_day_product_status", "missing": 0, "extra": 1}],
    }


class G4ExperimentPolicyTests(unittest.TestCase):
    def test_primary_preserves_extension_defaults(self):
        self.assertEqual(experiment_config("primary_default").aggregate_fast_path, None)
        self.assertIsNone(experiment_config("primary_default").merge_strategy)
        self.assertIsNone(experiment_config("primary_default").merge_strategy_threshold)

    def test_fast_path_off_is_separately_labelled_merge_comparison(self):
        config = experiment_config("comparison_fast_off_merge")
        self.assertFalse(config.aggregate_fast_path)
        self.assertEqual(config.merge_strategy, "merge")

    def test_fast_path_off_auto_is_separate_delete_insert_candidate(self):
        config = experiment_config("comparison_fast_off_auto")
        self.assertFalse(config.aggregate_fast_path)
        self.assertEqual(config.merge_strategy, "auto")
        self.assertEqual(config.merge_strategy_threshold, 1.0)

    def test_unknown_config_rejected(self):
        with self.assertRaises(ValueError):
            experiment_config("delete_insert")

    def test_wrong_database_rejected(self):
        with self.assertRaises(ValueError):
            validate_sql_safety("SELECT 1", database="aggregatex", scheduler_enabled=False)

    def test_enabled_scheduler_rejected(self):
        with self.assertRaises(ValueError):
            validate_sql_safety("SELECT 1", database="ax_g4_repro", scheduler_enabled=True)

    def test_destructive_sql_tripwire_rejected(self):
        with self.assertRaises(ValueError):
            validate_sql_safety("TRUNCATE ax.orders", database="ax_g4_repro", scheduler_enabled=False)

    def test_prepared_sql_keeps_primary_defaults_and_has_target_guards(self):
        trace = (PREP / "trace_refresh.sql").read_text()
        self.assertIn("'primary_default'", trace)
        self.assertIn("NO SET for aggregate_fast_path", trace)
        primary_branch = trace.split("SELECT :'experiment' <> 'primary_default'", 1)[0]
        primary_branch = "\n".join(
            line for line in primary_branch.splitlines() if not line.lstrip().startswith("--")
        )
        self.assertNotRegex(primary_branch, re.compile(r"(?im)^\s*SET\s+(LOCAL\s+)?pg_trickle\.(aggregate_fast_path|merge_strategy|merge_strategy_threshold)\b"))
        self.assertIn("current_database()='ax_g4_repro'", trace)
        self.assertIn("current_setting('pg_trickle.enabled',true)='off'", trace)
        self.assertIn("'comparison_fast_off_merge'", trace)
        self.assertIn("source_stable_name IS NOT NULL", trace)
        self.assertIn("STAGING_TRACE INCONCLUSIVE", trace)
        self.assertIn("AGGREGATE_DELTA_TRACE INCONCLUSIVE", trace)
        post_refresh_capture = trace.split("SELECT pgtrickle.refresh_stream_table", 1)[1]
        self.assertNotIn("ROLLBACK;\n  \\quit 4", post_refresh_capture)

    def test_fixture_and_case_scripts_have_hard_fixture_safety_checks(self):
        fixture = (PREP / "fixture.sql").read_text()
        cases = (PREP / "cases.sql").read_text()
        self.assertIn("current_database()='ax_g4_repro'", fixture)
        self.assertIn("current_setting('pg_trickle.enabled',true)='off'", fixture)
        self.assertIn("fixture_budget_ok", fixture)
        self.assertIn("B_update requires exactly one paid order 1002", cases)
        self.assertIn("'2026-11-20T12:00:00Z'", cases)

    def test_missing_stage_boundary_is_inconclusive(self):
        evidence = complete_evidence()
        evidence.pop("stage_before_compaction")
        self.assertEqual(classify_evidence(evidence), "INCONCLUSIVE")

    def test_requested_configuration_does_not_prove_actual_apply_path(self):
        evidence = complete_evidence()
        evidence.pop("apply_observed")
        evidence["requested_config"] = "comparison_fast_off_merge"
        self.assertEqual(classify_evidence(evidence), "INCONCLUSIVE")

    def test_unknown_vector_or_apply_path_is_inconclusive(self):
        evidence = complete_evidence()
        evidence["apply_observed"] = "merge_requested"
        self.assertEqual(classify_evidence(evidence), "INCONCLUSIVE")

    def test_no_runtime_execution_is_inconclusive(self):
        evidence = complete_evidence()
        evidence["runtime_executed"] = False
        self.assertEqual(classify_evidence(evidence), "INCONCLUSIVE")

    def test_frontier_or_fallback_mismatch_is_inconclusive(self):
        for mutate in (
            lambda e: e.update(frontiers_correlate=False),
            lambda e: e["refresh_history"].update(was_full_fallback=True),
            lambda e: e["refresh_history"].update(action="FULL"),
        ):
            evidence = complete_evidence()
            mutate(evidence)
            self.assertEqual(classify_evidence(evidence), "INCONCLUSIVE")

    def test_stage_negative_loss_can_only_be_localized_with_all_evidence(self):
        self.assertEqual(classify_evidence(complete_evidence()), "STAGING_DEFECT_CONFIRMED")

    def test_missing_negative_at_stage_boundary_does_not_confirm_staging(self):
        evidence = complete_evidence()
        evidence["stage_after_compaction"] = [{"change_id": 2, "action": "D", "order_id": 7}]
        self.assertEqual(classify_evidence(evidence), "INCONCLUSIVE")


if __name__ == "__main__":
    unittest.main()
