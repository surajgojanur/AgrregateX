-- Manual rollback of Issue #34, ONLY when the before-snapshot confirmed
-- ax_monitor had NO SELECT on this view before 002_monitor_health_view.sql.
-- Never run as an automatic teardown; unrelated privileges are left untouched.
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '10s';
DO $guard$
BEGIN
    IF current_database() <> 'aggregatex'
       OR current_user <> 'postgres'
       OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=current_user AND rolsuper)
       OR to_regclass('pgtrickle.stream_tables_info') IS NULL
       OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ax_monitor' AND NOT rolsuper AND NOT rolbypassrls)
    THEN
        RAISE EXCEPTION 'Wrong rollback target or migration role';
    END IF;
END
$guard$;
REVOKE SELECT ON TABLE pgtrickle.stream_tables_info FROM ax_monitor;
DO $verify$
BEGIN
    -- A remaining SELECT may be inherited or granted by a different role.
    IF has_table_privilege('ax_monitor','pgtrickle.stream_tables_info','SELECT') THEN
        RAISE EXCEPTION 'View remains readable through another privilege; investigate manually';
    END IF;
    IF has_table_privilege('ax_monitor','ax.orders','SELECT')
       OR has_table_privilege('ax_monitor','ax.products','SELECT') THEN
        RAISE EXCEPTION 'Unexpected tenant fact access during rollback';
    END IF;
END
$verify$;
COMMIT;
