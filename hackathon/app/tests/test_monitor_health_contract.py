"""Behavioral tests for incomplete and degraded diagnostic evidence."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from axapi import db, engine, monitor_health, monitoring


class MonitorHealthContractTests(unittest.TestCase):
    def read(self, rows):
        connection = Mock()
        connection.execute.return_value.fetchall.return_value = rows
        result = monitor_health.read_health(connection)
        connection.execute.assert_called_once_with(monitor_health.HEALTH_SQL)
        return result

    def complete(self):
        return [{"check_name": name, "severity": "OK", "detail": "Verified"}
                for name in sorted(monitor_health.REQUIRED_CHECKS)]

    def test_complete_ok_is_preserved(self):
        rows = self.complete()
        self.assertEqual(self.read(rows), rows)

    def test_missing_checks_empty_duplicates_and_malformed_are_unknown(self):
        complete = self.complete()
        for rows in ([], complete[1:], complete + complete[:1], complete + [None],
                     complete + [{"check_name": "extra", "severity": "invented", "detail": ""}]):
            with self.subTest(rows=rows):
                self.assertTrue(any(row["severity"] == "UNKNOWN" for row in self.read(rows)))

    def test_permission_exception_is_sanitized(self):
        connection = Mock()
        error = RuntimeError("secret stored SQL or credential")
        error.sqlstate = "42501"
        connection.execute.side_effect = error
        result = monitor_health.read_health(connection)
        self.assertEqual(result[0]["severity"], "UNKNOWN")
        self.assertIn("42501", result[0]["detail"])
        self.assertNotIn("secret", result[0]["detail"])

    def test_real_warnings_errors_unknown_and_empty_remain_degraded(self):
        fresh = [{"name": "stream", "status": "ACTIVE", "consecutive_errors": 0,
                  "age_s": 0.1, "verified_at": None}]
        for severity in ("OK", "WARN", "WARNING", "ERROR", "UNKNOWN", None):
            health = [] if severity is None else [{"check_name": "test", "severity": severity, "detail": ""}]
            snap = {"scheduler_running": True, "refresh_stats_5m": [], "health": health}
            with self.subTest(severity=severity), patch.dict(db.SHARDS, {"default": SimpleNamespace()}, clear=True):
                with patch.object(engine, "snapshot", return_value=snap), patch.object(db, "monitor") as connection:
                    connection.return_value.__enter__.return_value.execute.return_value.fetchall.return_value = fresh
                    state = monitoring.collect_shards()["shards"][0]["state"]
                self.assertEqual(state, "healthy" if severity == "OK" else "degraded")


if __name__ == "__main__":
    unittest.main()
