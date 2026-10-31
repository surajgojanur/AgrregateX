"""Offline tests for raw-source analytics; no PostgreSQL is started or mutated."""

import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("AX_AUTH_DISABLED", "0")
os.environ.pop("AX_ANALYTICS_READ_MODE", None)
os.environ.pop("AX_SHARDS", None)
os.environ.pop("AX_SHARD_DIRECTORY", None)

from fastapi.testclient import TestClient

from axapi import auth, config, db, engine, limits, main, queries, raw_queries

WINDOW = queries.Window(
    datetime(2026, 10, 30, 23, 30, tzinfo=UTC),
    datetime(2026, 11, 1, 1, 0, tzinfo=UTC),
    datetime(2026, 10, 31),
    datetime(2026, 11, 1),
    datetime(2026, 10, 31, tzinfo=UTC),
    datetime(2026, 11, 1, tzinfo=UTC),
)


class FakeConnection:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.sql = None
        self.params = None

    def execute(self, sql, params=None):
        self.sql, self.params = sql, params
        return self

    def fetchall(self):
        return self.rows

    @contextmanager
    def transaction(self):
        yield self


@contextmanager
def fake_tx(_role, _tenant):
    yield object()


class TestRawQueryFunctions(unittest.TestCase):
    def test_fedora_cancelled_only_product_has_no_raw_best_seller_row(self):
        # Independent source fixture: tenant 2 / product 116 has only the incident cancellation.
        orders = [
            {
                "tenant_id": 2,
                "product_id": 116,
                "status": "cancelled",
                "quantity": 1,
                "unit_price_cents": 14094,
            }
        ]
        expected = {
            "orders": len(orders),
            "cancelled": sum(o["status"] == "cancelled" for o in orders),
            "sale_orders": sum(
                o["status"] not in ("cancelled", "refunded") for o in orders
            ),
            "sales_cents": sum(
                o["quantity"] * o["unit_price_cents"]
                for o in orders
                if o["status"] not in ("cancelled", "refunded")
            ),
        }
        summary_rows = [
            {"status": "cancelled", "orders": 1, "units": 1, "gross_cents": 14094}
        ]
        summary = raw_queries.summary(FakeConnection(summary_rows), 2, WINDOW)
        top = raw_queries.top_products(FakeConnection([]), 2, WINDOW, 10)
        self.assertEqual(
            expected,
            {
                "orders": summary["orders"],
                "cancelled": summary["cancelled_or_refunded"],
                "sale_orders": summary["sale_orders"],
                "sales_cents": summary["sales_cents"],
            },
        )
        self.assertEqual(top, [])

    def test_summary_cancelled_fixture_excludes_revenue_and_preserves_cents(self):
        huge = 2**60 + 23
        rows = [
            {"status": "cancelled", "orders": 1, "units": 1, "gross_cents": 14094},
            {"status": "paid", "orders": 2, "units": 3, "gross_cents": huge},
            {"status": "shipped", "orders": 1, "units": 1, "gross_cents": 1299},
            {"status": "refunded", "orders": 1, "units": 1, "gross_cents": 4000},
        ]
        conn = FakeConnection(rows)
        actual = raw_queries.summary(conn, 2, WINDOW)
        self.assertEqual((actual["orders"], actual["sale_orders"]), (5, 3))
        self.assertEqual(actual["units_sold"], 4)
        self.assertEqual(actual["sales_cents"], huge + 1299)
        self.assertEqual(actual["cancelled_or_refunded"], 2)
        self.assertEqual(actual["cancel_rate"], 0.4)
        self.assertEqual(actual["by_status"]["cancelled"]["gross_cents"], 14094)
        self.assertIs(type(actual["sales_cents"]), int)
        self.assertEqual(conn.params, {"t": 2, "f": WINDOW.start, "to": WINDOW.end})

    def test_summary_empty_and_zero_sale_orders(self):
        self.assertEqual(raw_queries._summary_from_rows([])["by_status"], {})
        self.assertEqual(raw_queries._summary_from_rows([])["cancel_rate"], 0.0)
        all_cancelled = raw_queries._summary_from_rows(
            [{"status": "cancelled", "orders": 1, "units": 2, "gross_cents": 14094}]
        )
        self.assertEqual(
            (
                all_cancelled["sale_orders"],
                all_cancelled["sales_cents"],
                all_cancelled["avg_order_cents"],
                all_cancelled["units_sold"],
            ),
            (0, 0, 0, 0),
        )

    def test_raw_summary_is_one_tenant_scoped_bound_statement(self):
        conn = FakeConnection()
        raw_queries.summary(conn, 2, WINDOW)
        self.assertIn("FROM ax.orders", conn.sql)
        self.assertIn("tenant_id = %(t)s", conn.sql)
        self.assertIn("created_at >= %(f)s AND created_at < %(to)s", conn.sql)
        self.assertNotRegex(conn.sql, r"ax\.st_(day|hour)_")
        self.assertNotIn("tenant_id = 2", conn.sql)

    def test_day_and_hour_trends_use_utc_and_half_open_source_bounds(self):
        bucket = datetime(2026, 10, 31, 0, 0)
        for grain in ("day", "hour"):
            conn = FakeConnection(
                [
                    {
                        "bucket": bucket,
                        "orders": 1,
                        "sales_cents": 0,
                        "cancelled_or_refunded": 1,
                    }
                ]
            )
            actual = raw_queries.trends(conn, 2, WINDOW, grain)
            self.assertEqual(actual[0]["bucket"], "2026-10-31T00:00:00+00:00")
            self.assertIn("created_at >= %(f)s AND created_at < %(to)s", conn.sql)
            self.assertIn(
                f"date_trunc('{grain}', created_at AT TIME ZONE 'UTC')", conn.sql
            )
            self.assertNotRegex(conn.sql, r"ax\.st_(day|hour)_")
        self.assertEqual(raw_queries.trends(FakeConnection(), 2, WINDOW, "day"), [])
        with self.assertRaises(ValueError):
            raw_queries.trends(FakeConnection(), 2, WINDOW, "minute")

    def test_top_products_excludes_cancelled_and_breaks_sales_ties_by_id(self):
        conn = FakeConnection(
            [
                {
                    "product_id": 10,
                    "name": "A",
                    "category_id": 4,
                    "sales_cents": 100,
                    "units_sold": 1,
                    "orders": 1,
                },
                {
                    "product_id": 11,
                    "name": "B",
                    "category_id": 4,
                    "sales_cents": 100,
                    "units_sold": 1,
                    "orders": 1,
                },
            ]
        )
        rows = raw_queries.top_products(conn, 2, WINDOW, 2)
        self.assertEqual([r["rank"] for r in rows], [1, 2])
        self.assertIn("o.status NOT IN ('cancelled','refunded')", conn.sql)
        self.assertIn(
            "p.tenant_id = o.tenant_id AND p.product_id = o.product_id", conn.sql
        )
        self.assertIn("ORDER BY sales_cents DESC, p.product_id ASC", conn.sql)
        self.assertEqual(conn.params["t"], 2)
        self.assertEqual(conn.params["lim"], 2)
        self.assertNotRegex(conn.sql, r"ax\.st_(day|hour)_")

    def test_top_n_bounds_rejected(self):
        for limit in (0, 51, -1):
            with self.assertRaises(ValueError):
                raw_queries.top_products(FakeConnection(), 2, WINDOW, limit)

    def test_status_and_category_breakdowns_keep_contract_and_tenant_join(self):
        status_conn = FakeConnection(
            [{"key": "cancelled", "orders": 1, "units": 1, "gross_cents": 14094}]
        )
        self.assertEqual(
            raw_queries.breakdown(status_conn, 2, WINDOW, "status")[0]["gross_cents"],
            14094,
        )
        category_conn = FakeConnection(
            [{"key": 8, "orders": 1, "units": 0, "sales_cents": 0}]
        )
        self.assertEqual(
            raw_queries.breakdown(category_conn, 2, WINDOW, "category"),
            [{"key": 8, "orders": 1, "units": 0, "sales_cents": 0}],
        )
        self.assertIn(
            "p.tenant_id = o.tenant_id AND p.product_id = o.product_id",
            category_conn.sql,
        )
        self.assertIn("WHERE o.tenant_id = %(t)s", category_conn.sql)
        self.assertNotRegex(category_conn.sql, r"ax\.st_(day|hour)_")
        with self.assertRaises(ValueError):
            raw_queries.breakdown(FakeConnection(), 2, WINDOW, "unsafe")


class TestRawModeConfiguration(unittest.TestCase):
    def test_default_is_rollup(self):
        self.assertEqual(config.ANALYTICS_READ_MODE, "rollup")
        self.assertEqual(config.parse_analytics_read_mode(None), "rollup")
        self.assertEqual(config.parse_analytics_read_mode(""), "rollup")

    def test_raw_source_is_explicit_and_invalid_values_fail(self):
        self.assertEqual(config.parse_analytics_read_mode("raw_source"), "raw_source")
        with self.assertRaisesRegex(ValueError, "AX_ANALYTICS_READ_MODE"):
            config.parse_analytics_read_mode("raw")

    def test_tenant_tx_uses_api_pool_and_transaction_local_tenant_setting(self):
        calls = []
        connection = FakeConnection()

        class Pool:
            @contextmanager
            def connection(self):
                calls.append("api_pool")
                yield connection

        shard = SimpleNamespace(api=Pool(), writer=object())
        with (
            patch.object(db, "DIRECTORY", {2: "owner"}),
            patch.object(db, "SHARDS", {"owner": shard}),
            db.tenant_tx("api", 2) as actual,
        ):
            self.assertIs(actual, connection)
        self.assertEqual(calls, ["api_pool"])
        self.assertEqual(connection.sql, "SELECT set_config('ax.tenant_id', %s, true)")
        self.assertEqual(connection.params, ("2",))


class TestRawModeAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.cookie = auth.issue(auth.User("tenant2@demo.local", "tenant", 2))
        self.client.cookies.set(auth.COOKIE, self.cookie)
        self._patches = [
            patch.object(config, "AUTH_DISABLED", False),
            patch.object(config, "ANALYTICS_READ_MODE", "raw_source"),
            patch.object(db, "tenant_tx", fake_tx),
            patch.object(
                raw_queries,
                "summary",
                return_value={
                    "orders": 1,
                    "sale_orders": 0,
                    "units_sold": 0,
                    "sales_cents": 0,
                    "avg_order_cents": 0,
                    "cancelled_or_refunded": 1,
                    "cancel_rate": 1.0,
                    "by_status": {
                        "cancelled": {"orders": 1, "units": 1, "gross_cents": 14094}
                    },
                },
            ),
            patch.object(engine, "freshness_brief"),
        ]
        for p in self._patches:
            p.start()
        self.freshness = engine.freshness_brief

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()

    def test_raw_mode_selects_source_query_and_marks_provenance_without_rollup_freshness(
        self,
    ):
        response = self.client.get("/api/tenants/2/summary")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["summary"]["sales_cents"], 0)
        self.assertEqual(body["summary"]["cancelled_or_refunded"], 1)
        self.assertEqual(body["analytics_mode"], "raw_source")
        self.assertFalse(body["provenance"]["uses_stream_tables"])
        self.assertEqual(body["provenance"]["source_tables"], ["ax.orders"])
        self.assertEqual(
            body["provenance"]["consistency"], "single_sql_statement_snapshot"
        )
        self.assertIsNone(body["freshness"])
        self.assertIsNone(body["source"]["stream_table_range"])
        self.assertEqual(len(body["source"]["raw_edge_ranges"]), 1)
        self.freshness.assert_not_called()

    def test_all_four_routes_select_raw_query_families_and_preserve_payload_fields(
        self,
    ):
        with (
            patch.object(raw_queries, "summary", return_value={"orders": 0}),
            patch.object(raw_queries, "trends", return_value=[]) as trends,
            patch.object(raw_queries, "top_products", return_value=[]) as products,
            patch.object(raw_queries, "breakdown", return_value=[]) as breakdown,
        ):
            get = lambda path: self.client.get(path)
            responses = [
                get("/api/tenants/2/summary"),
                get("/api/tenants/2/trends?grain=hour"),
                get("/api/tenants/2/top-products?limit=10"),
                get("/api/tenants/2/breakdown?by=category"),
            ]
        self.assertTrue(all(response.status_code == 200 for response in responses))
        self.assertEqual(responses[0].json()["summary"], {"orders": 0})
        self.assertEqual(responses[1].json()["points"], [])
        self.assertEqual(responses[2].json()["products"], [])
        self.assertEqual(responses[3].json()["rows"], [])
        self.assertEqual(
            [response.json()["analytics_mode"] for response in responses],
            ["raw_source"] * 4,
        )
        self.assertEqual(
            responses[2].json()["provenance"]["source_tables"],
            ["ax.orders", "ax.products"],
        )
        self.assertEqual(
            responses[3].json()["provenance"]["source_tables"],
            ["ax.orders", "ax.products"],
        )
        trends.assert_called_once()
        products.assert_called_once()
        breakdown.assert_called_once()
        self.freshness.assert_not_called()

    def test_request_cannot_override_server_side_mode(self):
        response = self.client.get("/api/tenants/2/summary?mode=rollup")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["analytics_mode"], "raw_source")

    def test_authentication_required_and_tenant_mismatch_denied_before_routing(self):
        self.client.cookies.delete(auth.COOKIE)
        self.assertEqual(self.client.get("/api/tenants/2/summary").status_code, 401)
        self.client.cookies.set(auth.COOKIE, self.cookie)
        with patch.object(db, "shard_for", wraps=db.shard_for) as route:
            response = self.client.get("/api/tenants/1/summary")
        self.assertEqual(response.status_code, 403)
        route.assert_not_called()

    def test_signed_operator_retains_cross_tenant_read_semantics(self):
        admin = auth.issue(auth.User("admin@demo.local", "admin", None))
        self.client.cookies.set(auth.COOKIE, admin)
        with patch.object(raw_queries, "summary", return_value={"orders": 0}):
            response = self.client.get("/api/tenants/1/summary")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["analytics_mode"], "raw_source")

    def test_unavailable_owning_shard_is_503_without_fallback(self):
        @contextmanager
        def unavailable(_role, _tenant):
            raise db.ShardUnavailable("tenant-shard", "OperationalError")
            yield  # pragma: no cover

        with patch.object(db, "tenant_tx", unavailable):
            response = self.client.get("/api/tenants/2/summary")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["shard"], "tenant-shard")

    def test_rollup_remains_default_path_and_response_contract(self):
        with (
            patch.object(config, "ANALYTICS_READ_MODE", "rollup"),
            patch.object(main.queries, "summary", return_value={"orders": 0}),
            patch.object(
                engine, "freshness_brief", return_value={"healthy": True}
            ) as fresh,
        ):
            response = self.client.get("/api/tenants/2/summary")
        body = response.json()
        self.assertEqual(body["analytics_mode"], "rollup")
        self.assertTrue(body["provenance"]["uses_stream_tables"])
        self.assertIn("stream_table_range", body["source"])
        self.assertIn("raw_edge_ranges", body["source"])
        self.assertEqual(body["summary"], {"orders": 0})
        fresh.assert_called_once()

    def test_per_tenant_concurrency_limit_is_still_applied(self):
        started = threading.Event()
        release = threading.Event()

        def slow(*_args):
            started.set()
            release.wait(2)
            return {"orders": 1}

        with (
            patch.object(main.limits, "LIMITER", limits.TenantLimiter(1, 0.01)),
            patch.object(raw_queries, "summary", side_effect=slow),
            ThreadPoolExecutor(2) as executor,
        ):
            first = executor.submit(self.client.get, "/api/tenants/2/summary")
            self.assertTrue(started.wait(1))
            second = self.client.get("/api/tenants/2/summary")
            release.set()
            result = first.result(2)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(second.status_code, 429)


if __name__ == "__main__":
    unittest.main()
