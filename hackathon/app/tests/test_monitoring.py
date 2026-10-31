import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from axapi import auth, config, monitoring


class MonitoringTests(unittest.TestCase):
    def test_success_percentiles_exclude_errors_and_timeouts(self):
        m = monitoring.Metrics()
        for status, ms in [(200, 1), (200, 3), (500, 900), (504, 1000)]:
            m.record(status, ms)
        self.assertEqual(m.snapshot()["p95_ms"], 3)
        self.assertEqual([m.snapshot()[k] for k in ("success", "errors", "timeouts")], [2, 1, 1])

    def test_storage_is_bounded_and_expires(self):
        m = monitoring.Metrics(capacity=2, window_s=5)
        with patch.object(monitoring.time, "monotonic", return_value=10):
            for _ in range(5):
                m.record(200, 1)
            self.assertEqual(m.snapshot()["success"], 2)
        with patch.object(monitoring.time, "monotonic", return_value=16):
            self.assertIsNone(m.snapshot()["p50_ms"])

    def test_cache_coalesces_requests_and_expires(self):
        calls = []
        c = monitoring.ShardCache(lambda: calls.append(1) or {}, ttl=15)
        with patch.object(monitoring.time, "monotonic", return_value=10):
            c.get()
            c.get()
        self.assertEqual(len(calls), 1)
        with patch.object(monitoring.time, "monotonic", return_value=26):
            c.get()
        self.assertEqual(len(calls), 2)

    def test_secure_mode_requires_signed_operator(self):
        self.addCleanup(patch.stopall)
        patch.object(config, "AUTH_DISABLED", False).start()
        app = FastAPI()
        monitoring.install(app)
        client = TestClient(app)
        with patch.object(monitoring.cache, "get", return_value={"shards": []}) as collect:
            self.assertEqual(client.get("/api/monitoring").status_code, 401)
            client.cookies.set(auth.COOKIE, auth.issue(auth.User("tenant1@demo.local", "tenant", 1)))
            self.assertEqual(client.get("/api/monitoring").status_code, 403)
            collect.assert_not_called()
            client.cookies.set(auth.COOKIE, auth.issue(auth.User("admin@demo.local", "admin", None)))
            self.assertEqual(client.get("/api/monitoring").status_code, 200)
            collect.assert_called_once()

    def test_unreachable_shard_does_not_hide_healthy_shard(self):
        from axapi import db, engine
        from types import SimpleNamespace
        snap = {"scheduler_running": True, "refresh_stats_5m": [], "health": []}
        with patch.dict(db.SHARDS, {"a": SimpleNamespace(), "b": SimpleNamespace()}, clear=True), patch.object(engine, "snapshot", side_effect=[RuntimeError(), snap]):
            with patch.object(db, "monitor") as connection:
                connection.return_value.__enter__.return_value.execute.return_value.fetchall.return_value = []
                out = monitoring.collect_shards()
        self.assertEqual([s["state"] for s in out["shards"]], ["unavailable", "degraded"])


if __name__ == "__main__":
    unittest.main()
