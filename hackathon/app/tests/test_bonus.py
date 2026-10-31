"""Unit tests for B-1 (freshness in responses), B-2 (rebuild CLI argument handling) and B-3 (per-tenant
concurrency limit). No database: the DB layer is replaced with fakes. Live DB behaviour of B-2 is
covered by running `python -m axapi.rebuild` against a stack (see app/README.md).

run: cd hackathon/app && python -m unittest tests.test_bonus -v   (needs fastapi, httpx, psycopg)
"""
import os
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

os.environ.update(AX_AUTH_DISABLED="1", AX_TENANT_MAX_CONCURRENT="2", AX_TENANT_QUEUE_WAIT_S="0.1")
os.environ.pop("AX_SHARDS", None)
os.environ.pop("AX_SHARD_DIRECTORY", None)

from fastapi.testclient import TestClient  # noqa: E402

from axapi import db, engine, limits, main, queries, rebuild  # noqa: E402

engine._ORIG_BRIEF = engine.freshness_brief

BRIEF = {"verified_at": "2026-10-31T13:00:00+00:00", "age_s": 0.8, "healthy": True, "stream_tables": 3,
         "rule": "oldest stream table's last completed refresh"}


@contextmanager
def fake_tx(_role, _tenant):
    yield object()


class FakeDB(unittest.TestCase):
    def setUp(self):
        self._orig = (db.tenant_tx, engine.freshness_brief, queries.summary, queries.trends,
                      queries.top_products, queries.breakdown)
        db.tenant_tx = fake_tx
        engine.freshness_brief = lambda shard: BRIEF
        self.delay = 0.0
        slow = lambda *a, **k: (time.sleep(self.delay), {"orders": 1})[1]  # noqa: E731
        queries.summary = slow
        queries.trends = lambda *a: []
        queries.top_products = lambda *a: []
        queries.breakdown = lambda *a: []
        main.limits.LIMITER = limits.LIMITER = limits.TenantLimiter(2, 0.1)
        self.client = TestClient(main.app)

    def tearDown(self):
        (db.tenant_tx, engine.freshness_brief, queries.summary, queries.trends,
         queries.top_products, queries.breakdown) = self._orig


class TestB1Freshness(FakeDB):
    def test_every_analytics_response_carries_freshness(self):
        for path in ("summary", "trends", "top-products", "breakdown"):
            r = self.client.get(f"/api/tenants/1/{path}")
            self.assertEqual(r.status_code, 200, path)
            self.assertEqual(r.json()["freshness"], BRIEF, path)


class TestB3Limiter(FakeDB):
    def test_limit_rejects_excess_with_429_and_retry_after(self):
        self.delay = 0.6
        with ThreadPoolExecutor(6) as ex:
            rs = list(ex.map(lambda _: self.client.get("/api/tenants/1/summary"), range(6)))
        codes = sorted(r.status_code for r in rs)
        self.assertEqual(codes.count(200), 2, codes)   # exactly the 2 slots ran
        self.assertEqual(codes.count(429), 4, codes)
        busy = next(r for r in rs if r.status_code == 429)
        self.assertEqual(busy.headers.get("retry-after"), "1")
        self.assertEqual(busy.json()["tenant_id"], 1)

    def test_busy_tenant_does_not_starve_another_tenant(self):
        self.delay = 0.6
        with ThreadPoolExecutor(8) as ex:
            flood = [ex.submit(self.client.get, "/api/tenants/1/summary") for _ in range(6)]
            time.sleep(0.15)                      # tenant 1's slots are now full
            other = ex.submit(self.client.get, "/api/tenants/2/summary").result()
            [f.result() for f in flood]
        self.assertEqual(other.status_code, 200)

    def test_slot_released_after_error_and_counters(self):
        lim = limits.TenantLimiter(1, 0.05)
        with self.assertRaises(RuntimeError):
            with lim.slot(7):
                raise RuntimeError("query failed")
        with lim.slot(7):                         # would block forever if the slot leaked
            pass
        snap = lim.snapshot()["tenants"][0]
        self.assertEqual((snap["tenant_id"], snap["in_flight"], snap["admitted"], snap["peak"]), (7, 0, 2, 1))

    def test_rejection_counted_and_exposed(self):
        lim = limits.LIMITER
        hold = threading.Event()
        done = threading.Event()

        def holder():
            with lim.slot(3):
                with lim.slot(3):
                    hold.set()
                    done.wait(2)
        t = threading.Thread(target=holder)
        t.start()
        hold.wait(2)
        self.assertEqual(self.client.get("/api/tenants/3/summary").status_code, 429)
        done.set()
        t.join()
        row = next(x for x in self.client.get("/api/limits").json()["tenants"] if x["tenant_id"] == 3)
        self.assertGreaterEqual(row["rejected_429"], 1)
        self.assertEqual(row["in_flight"], 0)


GOOD_ST = [{"name": n, "rebuild_status": "COMPLETED", "status_after": "ACTIVE"} for n in rebuild.ST_NAMES]
GOOD_ORACLE = [{"stream_table": n.split(".")[1], "missing": 0, "extra": 0} for n in rebuild.ST_NAMES]


class TestB2VerifyFailClosed(unittest.TestCase):
    """PR #24 review: success needs EXACTLY the 3 stream tables, no duplicates, all counts 0."""

    def test_clean_exact_set_passes(self):
        self.assertEqual(rebuild.verify(GOOD_ST, GOOD_ORACLE), (True, True, []))

    def test_zero_oracle_rows_is_not_clean(self):
        rebuilt, clean, problems = rebuild.verify(GOOD_ST, [])
        self.assertFalse(clean)
        self.assertTrue(any("no rows" in p for p in problems))
        self.assertFalse(rebuild.verify(GOOD_ST, None)[1])

    def test_missing_oracle_row_is_not_clean(self):
        self.assertFalse(rebuild.verify(GOOD_ST, GOOD_ORACLE[:2])[1])

    def test_duplicate_oracle_row_is_not_clean(self):
        dup = GOOD_ORACLE[:2] + [GOOD_ORACLE[0]]
        self.assertFalse(rebuild.verify(GOOD_ST, dup)[1])

    def test_unexpected_oracle_row_is_not_clean(self):
        self.assertFalse(rebuild.verify(GOOD_ST, GOOD_ORACLE + [{"stream_table": "st_other", "missing": 0, "extra": 0}])[1])

    def test_nonzero_counts_are_not_clean(self):
        for k in ("missing", "extra"):
            bad = [dict(GOOD_ORACLE[0], **{k: 1})] + GOOD_ORACLE[1:]
            self.assertFalse(rebuild.verify(GOOD_ST, bad)[1], k)

    def test_rebuild_must_complete_for_every_table(self):
        self.assertFalse(rebuild.verify(GOOD_ST[:2], GOOD_ORACLE)[0])                       # one table missing
        timeout = [dict(GOOD_ST[0], rebuild_status="TIMEOUT")] + GOOD_ST[1:]
        self.assertFalse(rebuild.verify(timeout, GOOD_ORACLE)[0])
        suspended = [dict(GOOD_ST[0], status_after="SUSPENDED")] + GOOD_ST[1:]
        self.assertFalse(rebuild.verify(suspended, GOOD_ORACLE)[0])


class TestB1SingleFlight(unittest.TestCase):
    def test_concurrent_misses_run_one_query(self):
        calls = []
        orig = db.monitor

        class FakeConn:
            def execute(self, *_a):
                calls.append(1)
                time.sleep(0.2)
                return self

            def fetchall(self):
                return [{"verified_at": None, "age_s": None, "status": "ACTIVE"}]

        @contextmanager
        def fake_monitor(_shard):
            yield FakeConn()

        db.monitor = fake_monitor
        engine._brief_cache.clear()
        try:
            shard = next(iter(db.SHARDS.values()))
            with ThreadPoolExecutor(20) as ex:
                list(ex.map(lambda _: engine._ORIG_BRIEF(shard), range(20)))
        finally:
            db.monitor = orig
        self.assertEqual(len(calls), 1)


class TestB2RebuildCli(unittest.TestCase):
    def test_requires_owner_password(self):
        os.environ.pop("AX_DB_SUPERUSER_PASSWORD", None)
        self.assertEqual(rebuild.main(["--shard", "all"]), 2)

    def test_rejects_unknown_shard(self):
        os.environ["AX_DB_SUPERUSER_PASSWORD"] = "x"
        try:
            self.assertEqual(rebuild.main(["--shard", "zzz"]), 2)
        finally:
            os.environ.pop("AX_DB_SUPERUSER_PASSWORD", None)


if __name__ == "__main__":
    unittest.main()
