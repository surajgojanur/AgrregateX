"""B3: permission-negative and hostile probes against the 003 facade (disposable ax-mh39 only)."""
import json, sys
import psycopg
from psycopg.rows import dict_row
CB = sys.argv[1]
PW = {"ax_monitor": "local-demo-monitor", "ax_api": "local-demo-api", "ax_writer": "local-demo-writer",
      "mh39_probe": "mh39-probe-local", "postgres": "local-demo-superuser"}
def conn(user):
    return psycopg.connect(f"host=127.0.0.1 port=25590 dbname=aggregatex user={user} password={PW[user]}",
                           autocommit=True, row_factory=dict_row)
FACADE = "SELECT check_name, severity FROM ax.monitor_health_check() ORDER BY 1"
results = []
def probe(name, user, sql, expect, setup=()):
    with conn(user) as c:
        for s in setup: c.execute(s)
        try:
            cur = c.execute(sql)
            rows = cur.fetchall() if cur.description else []
            got = "OK"
            extra = rows
        except psycopg.Error as e:
            got, extra = e.sqlstate, None
    ok = (got == expect) if expect != "ROWS" else (got == "OK")
    results.append({"test": name, "user": user, "expected": expect, "got": got, "pass": ok})
    return extra
deny = "42501"
for rel in ["ax.orders", "ax.products", "ax.customers", "ax.st_day_product_status", "ax.st_day_category_status",
            "ax.st_hour_category_status", "pgtrickle.pgt_dependencies", "pgtrickle.pgt_change_tracking",
            "pgtrickle.pgt_window_states", "pgtrickle.pgt_outbox_config", "pgtrickle.pgt_scheduler_jobs",
            "pgtrickle.pgt_freshness_controller_state", "pgtrickle.pgt_publication_bindings", f"pgtrickle_changes.{CB}"]:
    probe(f"monitor SELECT {rel} denied", "ax_monitor", f"SELECT * FROM {rel} LIMIT 1", deny)
probe("monitor native health_check() denied", "ax_monitor", "SELECT * FROM pgtrickle.health_check()", deny)
probe("monitor change_buffer_sizes() denied", "ax_monitor", "SELECT * FROM pgtrickle.change_buffer_sizes()", deny)
probe("monitor SET ROLE ax_health_owner denied", "ax_monitor", "SET ROLE ax_health_owner", deny)
probe("monitor SET SESSION AUTHORIZATION denied", "ax_monitor", "SET SESSION AUTHORIZATION ax_health_owner", deny)
probe("monitor CREATE OR REPLACE facade denied", "ax_monitor",
      "CREATE OR REPLACE FUNCTION ax.monitor_health_check() RETURNS TABLE (check_name text, severity text, detail text) LANGUAGE sql AS $$ SELECT 'x','OK','x' $$", deny)
probe("monitor ALTER facade SECURITY INVOKER denied", "ax_monitor", "ALTER FUNCTION ax.monitor_health_check() SECURITY INVOKER", deny)
probe("monitor ALTER facade OWNER denied", "ax_monitor", "ALTER FUNCTION ax.monitor_health_check() OWNER TO ax_monitor", deny)
probe("monitor GRANT facade to ax_api (no grant option)", "ax_monitor", "GRANT EXECUTE ON FUNCTION ax.monitor_health_check() TO ax_api", "OK")
probe("ax_api still cannot execute after monitor GRANT attempt", "postgres",
      "SELECT 1 WHERE NOT has_function_privilege('ax_api', 'ax.monitor_health_check()', 'EXECUTE')", "ROWS")
for u in ["ax_api", "ax_writer", "mh39_probe"]:
    probe(f"{u} EXECUTE facade denied", u, FACADE, deny)
probe("superuser calling facade refused by session_user check", "postgres", FACADE, deny)
base = probe("monitor facade baseline", "ax_monitor", FACADE, "ROWS")
base_set = {(r["check_name"], r["severity"]) for r in base or []}
hostile = probe("hostile temp-table shadowing + search_path", "ax_monitor", FACADE, "ROWS", setup=[
    "CREATE TEMP TABLE pgt_stream_tables (pgt_schema text, pgt_name text, status text)",
    "INSERT INTO pgt_stream_tables VALUES ('ax','fake','ERROR')",
    "CREATE TEMP TABLE pg_stat_activity (backend_type text, datname text)",
    "SET search_path = pg_temp, pgtrickle, ax, public"])
# (fixed after the 2026-11-01 run, whose JSON shows FAIL here: it iterated dict keys, not rows)
hostile_set = {(r["check_name"], r["severity"]) for r in hostile or []}
results.append({"test": "hostile search_path result names/severities identical to baseline (modulo stale flaps)",
                "pass": {n for n, _ in hostile_set} == {n for n, _ in base_set} and
                        ("error_tables", "OK") in hostile_set})
for guc, val in [("pg_trickle.parallel_refresh_mode", "off"), ("pg_trickle.disk_headroom_mb", "0"),
                 ("pg_trickle.change_buffer_schema", "public"), ("row_security", "off")]:
    try:
        rows = probe(f"monitor SET {guc}={val} then facade", "ax_monitor", FACADE, "ROWS", setup=[f"SET {guc} = '{val}'"])
        results[-1]["observed"] = sorted({(r["check_name"], r["severity"]) for r in rows or []} ^ base_set)
    except psycopg.Error as e:
        results.append({"test": f"monitor SET {guc}={val}", "got": e.sqlstate, "note": "SET refused"})
probe("statement_timeout 1ms -> error propagates (app sanitises)", "ax_monitor", FACADE, "57014",
      setup=["SET statement_timeout = '1ms'"])
print(json.dumps(results, indent=1, default=str))
