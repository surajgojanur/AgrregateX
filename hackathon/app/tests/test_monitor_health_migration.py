"""Static guardrails for the human-gated monitor-view migration.

These checks review the SQL text; they do not execute the migration or prove
PostgreSQL runtime behavior. Runtime verification is the separate read-only SQL.
"""
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "sql/migrations/002_monitor_health_view.sql"
VERIFY = ROOT / "sql/migrations/002_monitor_health_view_verify.sql"
ROLLBACK = ROOT / "sql/migrations/002_monitor_health_view_rollback.sql"


class MonitorHealthMigrationTests(unittest.TestCase):
    def test_migration_is_transactional_and_grants_one_view_privilege(self):
        sql = MIGRATION.read_text()
        grants = re.findall(r"^\s*GRANT\s+([^;]+);", sql, flags=re.IGNORECASE | re.MULTILINE)
        self.assertEqual(grants, ["SELECT ON TABLE pgtrickle.stream_tables_info TO ax_monitor"])
        self.assertIn("BEGIN;", sql)
        self.assertIn("COMMIT;", sql)
        self.assertIn("SET LOCAL lock_timeout = '2s';", sql)
        self.assertIn("SET LOCAL statement_timeout = '10s';", sql)
        self.assertNotRegex(sql, r"(?im)^\s*(?:ALTER\s+ROLE|CREATE\s+ROLE|DROP\s+|TRUNCATE\s|DELETE\s+FROM|UPDATE\s+)")

    def test_guard_pins_database_engine_view_semantics_and_least_privilege(self):
        sql = MIGRATION.read_text()
        for required in (
            "current_database() <> 'aggregatex'",
            "current_setting('server_version_num')::integer <> 180006",
            "extversion = '0.108.3'",
            "a0db0c17e25f761c7d978515ce0cce6c",
            "pgtrickle.parse_duration_seconds(text)",
            "has_table_privilege('ax_monitor','ax.orders','SELECT')",
            "has_table_privilege('ax_monitor','ax.products','SELECT')",
            "has_table_privilege('ax_api','pgtrickle.stream_tables_info','SELECT')",
            "has_table_privilege('ax_writer','pgtrickle.stream_tables_info','SELECT')",
            "a.grantee = 0 AND a.privilege_type = 'SELECT'",
            "pg_has_role('ax_monitor', r.oid, 'SET')",
        ):
            with self.subTest(required=required):
                self.assertIn(required, sql)

    def test_verifier_is_read_only_and_rejects_raw_fact_access(self):
        sql = VERIFY.read_text()
        self.assertIn("BEGIN READ ONLY;", sql)
        self.assertIn("current_user <> 'ax_monitor'", sql)
        self.assertIn("NOT rolsuper AND NOT rolbypassrls", sql)
        self.assertIn("has_table_privilege(current_user,'ax.orders','SELECT')", sql)
        self.assertIn("has_table_privilege(current_user,'ax.products','SELECT')", sql)
        self.assertIn("pg_has_role(current_user, r.oid, 'SET')", sql)
        self.assertIn("ROLLBACK;", sql)

    def test_rollback_only_revokes_exact_view_grant(self):
        sql = ROLLBACK.read_text()
        revokes = re.findall(r"^\s*REVOKE\s+([^;]+);", sql, flags=re.IGNORECASE | re.MULTILINE)
        self.assertEqual(revokes, ["SELECT ON TABLE pgtrickle.stream_tables_info FROM ax_monitor"])
        self.assertIn("BEGIN;", sql)
        self.assertIn("COMMIT;", sql)


if __name__ == "__main__":
    unittest.main()
