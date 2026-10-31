"""Static security invariants; not a substitute for disposable database tests."""
import hashlib
import json
import re
import unittest
from pathlib import Path


SQL = Path(__file__).resolve().parents[2] / "sql/migrations"


class MonitorDependencyMigrationTests(unittest.TestCase):
    def test_every_003_file_has_an_independent_approval_hold(self):
        paths = sorted(SQL.glob("003_monitor_health_*.sql"))
        self.assertEqual(len(paths), 6)
        for path in paths:
            text = path.read_text()
            with self.subTest(path=path.name):
                self.assertIn("\\set ON_ERROR_STOP on", text)
                hold = re.search(r"DO \$(deployment_blocked|rollback_blocked|review_only_hold)\$(.*?)\$\1\$;", text, re.S)
                self.assertIsNotNone(hold)
                self.assertIn("RAISE EXCEPTION", hold.group(2))
                self.assertNotRegex(hold.group(2), r"\bIF\b")
                for mutation in re.finditer(r"(?m)^(?:CREATE |GRANT |REVOKE |ALTER |DROP )", text):
                    self.assertLess(hold.start(), mutation.start())

    def test_deployment_holds_precede_all_mutations(self):
        for name, operation in (("dependencies", "CREATE ROLE"),
                                ("dependencies_rollback", "DROP FUNCTION")):
            text = (SQL / f"003_monitor_health_{name}.sql").read_text()
            self.assertLess(text.index("RAISE EXCEPTION"), text.index(operation))
            self.assertIn("\\set ON_ERROR_STOP on", text)
            self.assertIn("BEGIN;", text)
            self.assertIn("COMMIT;", text)
            self.assertNotIn("CASCADE", text)

    def test_exact_column_allowlist_and_rollback_are_consistent(self):
        migration = (SQL / "003_monitor_health_dependencies.sql").read_text()
        rollback = (SQL / "003_monitor_health_dependencies_rollback.sql").read_text()
        guards = (SQL / "003_monitor_health_guards.sql").read_text()
        catalog_json = re.search(r"catalogs constant jsonb := '(.*?)';", guards, re.S).group(1)
        expected = {name: set(columns) for name, columns in json.loads(catalog_json).items()}
        def projections(text, verb, direction):
            matches = re.findall(rf"{verb} SELECT \((.*?)\)\s+ON TABLE pgtrickle\.(\w+) {direction} ax_health_owner;", text, re.S)
            return {name: set(re.split(r",\s*", columns.strip())) for columns, name in matches}
        self.assertEqual(projections(migration, "GRANT", "TO"), expected)
        self.assertEqual(projections(rollback, "REVOKE", "FROM"), expected)
        self.assertEqual(len(expected["pgt_dependencies"]), 14)
        self.assertNotRegex(migration, r"GRANT SELECT ON|ALL TABLES|TO PUBLIC|TO ax_api|TO ax_writer")
        self.assertEqual(re.findall(r"GRANT .* TO ax_monitor;", migration),
                         ["GRANT EXECUTE ON FUNCTION ax.monitor_health_check() TO ax_monitor;"])

    def test_missing_dependency_columns_fail_closed_and_body_is_pinned(self):
        function = (SQL / "003_monitor_health_function.sql").read_text()
        guards = (SQL / "003_monitor_health_guards.sql").read_text()
        body = function.split("$monitor_health$")[1]
        fingerprint = hashlib.md5(re.sub(r"\s+", "", body).encode()).hexdigest()
        self.assertIn(fingerprint, guards)
        self.assertIn("has_column_privilege(current_user, relation.oid, attribute.attnum, 'SELECT')", function)
        self.assertIn("IF missing_count <> 0", function)
        self.assertIn("'monitor_contract', 'UNKNOWN'", function)
        self.assertIn("session_user <> 'ax_monitor'", function)
        self.assertIn("current_user <> 'ax_health_owner'", function)
        self.assertIn("VOLATILE SECURITY DEFINER", function)
        self.assertIn("SET search_path = pg_catalog, pg_temp", function)


if __name__ == "__main__":
    unittest.main()
