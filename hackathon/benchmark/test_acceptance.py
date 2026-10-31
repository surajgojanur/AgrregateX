import unittest
from acceptance import verdict

class AcceptanceTests(unittest.TestCase):
    def test_missing_is_not_pass(self):
        r = verdict({})
        self.assertFalse(r["official_pass"])
        self.assertEqual(set(r["requirements"].values()), {"NOT TESTED"})

    def test_thresholds_are_strict(self):
        r = verdict({"http_ms": [200], "commit_visible_seconds": [30],
                     "oracle_mismatches": [1]})["requirements"]
        self.assertEqual([r[k] for k in ("G-1", "G-2", "G-4")], ["FAILED"] * 3)

    def test_invalid_measurements_fail(self):
        for value in (float("nan"), float("inf"), -1, True, "1"):
            self.assertEqual(verdict({"http_ms": [value]})["requirements"]["G-1"], "FAILED")

    def test_representative_never_official(self):
        self.assertFalse(verdict({"http_ms": [1]})["official_pass"])

    def test_safety_requires_repeats_and_both_metrics(self):
        pair = {"baseline_ms": 1, "dashboard_ms": 1.01,
                "baseline_tps": 100, "dashboard_tps": 95}
        self.assertEqual(verdict({"safety_pairs": [pair]*5})["requirements"]["G-3"], "VERIFIED")
        self.assertEqual(verdict({"safety_pairs": [pair]})["requirements"]["G-3"], "FAILED")
