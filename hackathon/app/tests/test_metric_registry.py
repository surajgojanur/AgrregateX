"""B-4 config-driven metrics: offline tests (no PostgreSQL is started or mutated).

run: cd hackathon/app && python -m unittest tests.test_metric_registry -v
Live acceptance against a real two-shard stack: tests/live_b4_check.py.
"""
import copy
import json
import os
import tempfile
import time
import unittest
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

os.environ.pop("AX_ANALYTICS_READ_MODE", None)
os.environ.pop("AX_SHARDS", None)
os.environ.pop("AX_SHARD_DIRECTORY", None)

from fastapi.testclient import TestClient  # noqa: E402

from axapi import auth, config, db, engine, limits, main, metric_registry as mr, queries  # noqa: E402

SHIPPED = Path(__file__).resolve().parent.parent / "config" / "metrics.json"
BASE = json.loads(SHIPPED.read_text())
NEW_METRIC = {   # the metric the live demo adds by editing ONLY the config file
    "id": "pending_share_pct", "label": "Pending order share", "type": "ratio", "unit": "percent",
    "numerator": {"measure": "orders", "statuses": ["pending"]},
    "denominator": {"measure": "orders", "statuses": "all"},
    "scale": 100, "decimals": 2, "group_by": ["total", "day"]}


def cfg(**changes):
    doc = copy.deepcopy(BASE)
    doc.update(changes)
    return doc


def with_metric(extra: dict, **changes):
    doc = cfg(**changes)
    doc["metrics"].append(extra)
    return doc


def errors_of(doc) -> list[str]:
    try:
        mr.parse(doc if isinstance(doc, str) else json.dumps(doc))
    except mr.ConfigError as exc:
        return exc.errors
    return []


def rows(*items):
    return [{"k": k, "status": s, "orders": n, "units": u, "gross_cents": c} for k, s, n, u, c in items]


class TestValidation(unittest.TestCase):
    def test_shipped_config_is_valid(self):
        reg = mr.parse(SHIPPED.read_text())
        self.assertEqual(reg.version, 1)
        self.assertEqual(set(reg.metrics), {"average_order_value", "cancel_rate_pct", "units_sold"})

    def test_new_metric_is_valid(self):
        self.assertEqual(errors_of(with_metric(NEW_METRIC)), [])

    def test_rejections(self):
        def m(**kv):
            out = copy.deepcopy(NEW_METRIC)
            out.update(kv)
            return {k: v for k, v in out.items() if v is not None}
        cases = {
            "unknown key 'sql'": with_metric(m(sql="SELECT 1")),
            "unknown key 'expression'": with_metric(m(expression="a/b")),
            "'customer' needs a rollup that does not exist": with_metric(m(group_by=["customer"])),
            "'distinct_customers' is not an allowed field": with_metric(
                m(numerator={"measure": "distinct_customers"})),
            "'line_cents' is not an allowed field": with_metric(m(numerator={"measure": "line_cents"})),
            "'ax.orders.status' is not an allowed field": with_metric(m(numerator={"measure": "ax.orders.status"})),
            "unknown or duplicate status": with_metric(m(numerator={"measure": "orders", "statuses": ["lost"]})),
            "unknown or duplicate status in ['paid', 'paid']": with_metric(
                m(numerator={"measure": "orders", "statuses": ["paid", "paid"]})),
            "'everything' is not one of": with_metric(m(numerator={"measure": "orders", "statuses": "everything"})),
            "needs a denominator": with_metric(m(denominator=None)),
            "must not have a denominator": with_metric(m(type="sum", scale=1)),
            "a 'sum' metric must use scale 1": with_metric(m(type="sum", denominator=None)),
            "scale: must be one of": with_metric(m(scale=7)),
            "decimals: an integer from 0 to 4": with_metric(m(decimals=9)),
            "type: 'avg' is not": with_metric(m(type="avg")),
            "unit: 'usd' is not": with_metric(m(unit="usd")),
            ".id: must match": with_metric(m(id="x; DROP TABLE ax.orders")),
            "duplicate id": with_metric(m(id="units_sold")),
            "config.schema": cfg(schema="other/v9"),
            "config.version": cfg(version="1"),
            "config.metrics: a non-empty list": cfg(metrics=[]),
            "unknown key 'sql'​": None,  # placeholder removed below
        }
        cases.pop("unknown key 'sql'​")
        for expect, doc in cases.items():
            with self.subTest(expect):
                errs = errors_of(doc)
                self.assertTrue(any(expect in e for e in errs), errs)

    def test_not_json_nan_and_size_are_rejected(self):
        self.assertTrue(errors_of("{not json")[0].startswith("not valid JSON"))
        nan = json.dumps(with_metric(NEW_METRIC)).replace('"decimals": 2', '"decimals": NaN')
        self.assertTrue(errors_of(nan)[0].startswith("not valid JSON"))
        self.assertIn("larger than", errors_of(" " * (mr.MAX_CONFIG_BYTES + 1))[0])

    def test_boolean_is_not_an_integer(self):
        self.assertTrue(errors_of(with_metric({**NEW_METRIC, "scale": True})))
        self.assertTrue(errors_of(cfg(version=True)))

    def test_one_bad_metric_rejects_the_whole_file(self):
        with self.assertRaises(mr.ConfigError):
            mr.parse(json.dumps(with_metric({**NEW_METRIC, "group_by": ["region"]})))


class TestFixedSql(unittest.TestCase):
    def test_sql_is_constant_and_parameterised(self):
        for g, by_mode in mr.SQL.items():
            for mode, sql in by_mode.items():
                with self.subTest(g=g, mode=mode):
                    self.assertIn("%(t)s", sql)
                    self.assertNotIn("{", sql)
                    self.assertEqual(sql, mr.SQL[g][mode])
        self.assertNotIn("ax.st_", mr.SQL["day"]["raw_source"])

    def test_config_text_never_reaches_sql(self):
        marker = "zz_marker_q"
        reg = mr.parse(json.dumps(with_metric({**NEW_METRIC, "id": marker, "label": marker, "description": marker})))
        conn = FakeConn()
        for g in reg.metrics[marker].group_by:
            mr.fetch(conn, 2, WINDOW, g, "rollup")
            self.assertNotIn(marker, conn.sql)

    def test_every_grouping_reads_an_existing_stream_table(self):
        existing = {"ax.st_day_product_status", "ax.st_day_category_status", "ax.st_hour_category_status"}
        self.assertTrue({g.stream_table for g in mr.GROUPINGS.values()} <= existing)
        self.assertEqual(mr.source_tables("category", "raw_source"), ["ax.orders", "ax.products"])
        self.assertEqual(mr.source_tables("hour", "rollup"), ["ax.st_hour_category_status", "ax.orders"])


class TestEvaluate(unittest.TestCase):
    reg = mr.parse(json.dumps(with_metric(NEW_METRIC)))

    def test_ratio_over_statuses(self):
        r = rows(("total", "paid", 3, 5, 3000), ("total", "shipped", 1, 1, 1001),
                 ("total", "cancelled", 2, 2, 999), ("total", "pending", 4, 4, 400))
        out = mr.evaluate(self.reg.metrics["average_order_value"], r, "total", 20)
        # sale = pending+paid+shipped: (3000+1001+400) / (3+1+4) = 550.125 -> 550
        self.assertEqual(out["total"], {"numerator": 4401, "denominator": 8, "value": 550})
        cr = mr.evaluate(self.reg.metrics["cancel_rate_pct"], r, "total", 20)["total"]
        self.assertEqual((cr["numerator"], cr["denominator"], cr["value"]), (2, 10, 20.0))
        ps = mr.evaluate(self.reg.metrics["pending_share_pct"], r, "total", 20)["total"]
        self.assertEqual(ps["value"], 40.0)

    def test_half_up_rounding(self):
        r = rows(("total", "paid", 2, 2, 3))   # 1.5 -> 2
        self.assertEqual(mr.evaluate(self.reg.metrics["average_order_value"], r, "total", 20)["total"]["value"], 2)

    def test_division_by_zero_is_explicit(self):
        r = rows(("total", "cancelled", 2, 2, 50))
        out = mr.evaluate(self.reg.metrics["average_order_value"], r, "total", 20)["total"]
        self.assertEqual((out["value"], out["undefined_reason"], out["denominator"]), (None, "denominator_zero", 0))
        empty = mr.evaluate(self.reg.metrics["average_order_value"], [], "total", 20)
        self.assertEqual(empty["total"]["value"], None)
        self.assertEqual(empty["rows"], [])

    def test_grouped_rows_sorted_and_total_is_whole_window(self):
        d1, d2 = datetime(2026, 10, 31), datetime(2026, 10, 30)
        r = rows((d1, "paid", 1, 3, 10), (d2, "paid", 1, 2, 10), (d2, "cancelled", 1, 9, 10))
        out = mr.evaluate(self.reg.metrics["units_sold"], r, "day", 20)
        self.assertEqual([p["key"] for p in out["rows"]], ["2026-10-30T00:00:00+00:00", "2026-10-31T00:00:00+00:00"])
        self.assertEqual([p["value"] for p in out["rows"]], [2, 3])
        self.assertEqual(out["total"]["value"], 5)

    def test_product_limit_truncates_rows_not_total(self):
        r = rows(*[(pid, "paid", 1, pid, 1) for pid in range(1, 31)])
        out = mr.evaluate(self.reg.metrics["units_sold"], r, "product", 5)
        self.assertEqual([p["key"] for p in out["rows"]], [30, 29, 28, 27, 26])
        self.assertTrue(out["truncated"])
        self.assertEqual((out["row_count"], out["total"]["value"]), (30, sum(range(1, 31))))


class TestHotReload(unittest.TestCase):
    def test_edit_invalid_fix(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "metrics.json")
            p.write_text(json.dumps(cfg()))
            holder = mr.RegistryFile(p)
            self.assertNotIn("pending_share_pct", holder.get().metrics)
            self.assertEqual(holder.get().version, 1)
            self.assertEqual(holder.loads, 1)                      # unchanged file is not re-read
            _rewrite(p, with_metric(NEW_METRIC, version=2))
            self.assertIn("pending_share_pct", holder.get().metrics)
            self.assertEqual(holder.get().version, 2)
            _rewrite(p, with_metric({**NEW_METRIC, "group_by": ["customer"]}, version=3))
            with self.assertRaises(mr.ConfigError) as ctx:
                holder.get()
            self.assertTrue(any("customer" in e for e in ctx.exception.errors))
            with self.assertRaises(mr.ConfigError):               # stays closed, no stale registry
                holder.get()
            _rewrite(p, with_metric(NEW_METRIC, version=4))
            self.assertEqual(holder.get().version, 4)
            p.unlink()
            with self.assertRaises(mr.ConfigError) as ctx:
                holder.get()
            self.assertIn("missing", ctx.exception.errors[0])


def _rewrite(p: Path, doc):
    tmp = p.with_suffix(".tmp")                # editors replace the file: new inode, maybe same size
    tmp.write_text(json.dumps(doc, indent=1))
    os.replace(tmp, p)
    time.sleep(0.01)


WINDOW = queries.split(datetime(2026, 10, 1, 6, tzinfo=UTC), datetime(2026, 10, 10, 18, tzinfo=UTC), "day")


class FakeConn:
    def __init__(self, result=()):
        self.result, self.sql, self.params = list(result), None, None

    def execute(self, sql, params=None):
        self.sql, self.params = sql, params
        return self

    def fetchall(self):
        return self.result


class TestApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name, "metrics.json")
        self.path.write_text(json.dumps(with_metric(NEW_METRIC)))
        self.conn = FakeConn(rows(("total", "paid", 4, 4, 1000), ("total", "pending", 1, 1, 100)))
        self.routed = []

        @contextmanager
        def tx(role, tenant):
            self.routed.append((role, tenant))
            yield self.conn
        self.patches = [patch.object(mr, "REGISTRY", mr.RegistryFile(self.path)),
                        patch.object(db, "tenant_tx", tx),
                        patch.object(engine, "freshness_brief", lambda shard: {"age_s": 0.5}),
                        patch.object(config, "AUTH_DISABLED", False),
                        patch.object(main.limits, "LIMITER", limits.TenantLimiter(4, 0.1))]
        for p in self.patches:
            p.start()
        self.client = TestClient(main.app)
        self.login(auth.User("tenant2@demo.local", "tenant", 2))

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def login(self, user):
        self.client.cookies.set(auth.COOKIE, auth.issue(user))

    URL = "/api/tenants/2/metrics/pending_share_pct?from=2026-10-01T06:00:00Z&to=2026-10-10T18:00:00Z"

    def test_listing_requires_login_and_lists_config(self):
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/api/metrics").status_code, 401)
        self.login(auth.User("tenant2@demo.local", "tenant", 2))
        body = self.client.get("/api/metrics").json()
        self.assertEqual(body["kind"], "derived_from_existing_stream_tables")
        self.assertIn("pending_share_pct", [m["id"] for m in body["metrics"]])

    def test_query_exact_window_provenance_and_value(self):
        r = self.client.get(self.URL)
        self.assertEqual(r.status_code, 200, r.text)
        b = r.json()
        self.assertEqual(b["total"], {"numerator": 1, "denominator": 5, "value": 20.0})
        self.assertEqual(b["source"]["stream_table_range"],
                         ["2026-10-02T00:00:00+00:00", "2026-10-10T00:00:00+00:00"])
        self.assertEqual(b["source"]["raw_edge_ranges"],
                         [["2026-10-01T06:00:00+00:00", "2026-10-02T00:00:00+00:00"],
                          ["2026-10-10T00:00:00+00:00", "2026-10-10T18:00:00+00:00"]])
        self.assertEqual(b["provenance"]["source_tables"], ["ax.st_day_product_status", "ax.orders"])
        self.assertEqual((b["registry_version"], b["freshness"], b["shard"]), (1, {"age_s": 0.5}, "default"))
        self.assertEqual(self.routed, [("api", 2)])
        self.assertEqual(self.conn.params["t"], 2)

    def test_cross_tenant_is_403_before_any_query(self):
        r = self.client.get(self.URL.replace("/tenants/2/", "/tenants/3/"))
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.routed, [])

    def test_unknown_metric_bad_grouping_bad_window(self):
        self.assertEqual(self.client.get("/api/tenants/2/metrics/nope").status_code, 404)
        r = self.client.get(self.URL + "&group_by=product")
        self.assertEqual(r.status_code, 422)
        self.assertIn("total, day", r.json()["detail"])
        self.assertEqual(self.client.get(self.URL + "&group_by=customer").status_code, 422)
        long_hour = "/api/tenants/2/metrics/cancel_rate_pct?group_by=hour&from=2026-08-01T00:00:00Z&to=2026-10-01T00:00:00Z"
        self.assertEqual(self.client.get(long_hour).status_code, 422)
        self.assertEqual(self.client.get(self.URL.replace("2026-10-01T06", "2026-12-01T06")).status_code, 422)
        self.assertEqual(self.routed, [])

    def test_invalid_config_fails_closed_with_errors_and_other_endpoints_survive(self):
        _rewrite(self.path, with_metric({**NEW_METRIC, "sql": "SELECT * FROM ax.orders"}, version=9))
        for url in ("/api/metrics", self.URL):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 503)
            self.assertTrue(any("'sql'" in e for e in r.json()["detail"]["errors"]))
        self.assertEqual(self.routed, [])
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)

    def test_raw_source_mode_reads_only_orders(self):
        with patch.object(config, "ANALYTICS_READ_MODE", "raw_source"):
            b = self.client.get(self.URL).json()
        self.assertEqual(b["provenance"]["source_tables"], ["ax.orders"])
        self.assertFalse(b["provenance"]["uses_stream_tables"])
        self.assertIsNone(b["freshness"])
        self.assertNotIn("ax.st_", self.conn.sql)

    def test_two_shard_routing_uses_the_tenant_shard(self):
        a, b = db.Shard.__new__(db.Shard), db.Shard.__new__(db.Shard)
        a.name, b.name = "a", "b"
        with patch.object(db, "DIRECTORY", {2: "b", 3: "a"}), patch.object(db, "SHARDS", {"a": a, "b": b}):
            body = self.client.get(self.URL).json()
            self.assertEqual(body["shard"], "b")
            self.login(auth.User("admin@demo.local", "admin", None))
            self.assertEqual(self.client.get("/api/tenants/99/metrics/units_sold").status_code, 404)
        self.assertEqual(self.routed, [("api", 2)])


if __name__ == "__main__":
    unittest.main()
