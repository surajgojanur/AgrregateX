\set ON_ERROR_STOP on
-- REVIEW ONLY: migration 003 is NOT APPLIED and has no deployment approval.
-- This independent hold also blocks standalone includes and diagnostic scripts.
DO $review_only_hold$
BEGIN
    RAISE EXCEPTION 'DEPLOYMENT APPROVAL HOLD: migration 003 requires separate reviewed authorization; do not execute this proposal or its includes.';
END
$review_only_hold$;

BEGIN READ ONLY;
SET LOCAL statement_timeout = '2s';
SET LOCAL lock_timeout = '1s';
SET LOCAL idle_in_transaction_session_timeout = '15s';
SET LOCAL search_path = pg_catalog, pg_temp;

DO $verify$
DECLARE
    diagnostic_oid oid;
    protected_relation record;
    probe_succeeded boolean;
BEGIN
    IF current_database() <> 'aggregatex' OR current_user <> 'ax_monitor' OR session_user <> 'ax_monitor'
       OR current_setting('server_version_num')::integer <> 180006
       OR NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trickle' AND extversion = '0.108.3')
       OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = current_user AND rolcanlogin
                     AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication) THEN
        RAISE EXCEPTION 'Verification requires an actual ax_monitor login to the independently verified target';
    END IF;
    SELECT oid INTO diagnostic_oid FROM pg_roles WHERE rolname = 'ax_health_owner' AND NOT rolcanlogin
        AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication;
    IF diagnostic_oid IS NULL OR pg_has_role(current_user, diagnostic_oid, 'SET')
       OR pg_has_role(current_user, diagnostic_oid, 'USAGE')
       OR EXISTS (SELECT 1 FROM pg_auth_members WHERE roleid = diagnostic_oid)
       OR has_schema_privilege(current_user, 'pgtrickle_changes', 'USAGE')
       OR NOT has_function_privilege(current_user, 'ax.monitor_health_check()', 'EXECUTE')
       OR has_function_privilege('ax_api', 'ax.monitor_health_check()', 'EXECUTE')
       OR has_function_privilege('ax_writer', 'ax.monitor_health_check()', 'EXECUTE')
       OR EXISTS (
           SELECT 1 FROM pg_proc procedure CROSS JOIN LATERAL aclexplode(procedure.proacl) acl
            WHERE procedure.oid = 'ax.monitor_health_check()'::regprocedure AND acl.grantee = 0
       ) THEN
        RAISE EXCEPTION 'Facade/private-role boundary verification failed';
    END IF;
    FOR protected_relation IN
        SELECT relation.oid, namespace.nspname, relation.relname
          FROM pg_class relation JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
         WHERE (namespace.nspname = 'ax' AND (relation.relname IN ('orders', 'products')
               OR relation.oid IN (SELECT pgt_relid FROM pgtrickle.pgt_stream_tables WHERE pgt_schema = 'ax')))
            OR (namespace.nspname = 'pgtrickle' AND relation.relname IN (
               'pgt_dependencies', 'pgt_change_tracking', 'pgt_window_states', 'pgt_outbox_config',
               'pgt_scheduler_jobs', 'pgt_freshness_controller_state', 'pgt_publication_bindings'))
    LOOP
        IF has_table_privilege(current_user, protected_relation.oid, 'SELECT')
           OR has_any_column_privilege(current_user, protected_relation.oid, 'SELECT') THEN
            RAISE EXCEPTION 'Unexpected direct row/column access for monitor';
        END IF;
        probe_succeeded := false;
        BEGIN
            EXECUTE format('SELECT * FROM %I.%I LIMIT 0', protected_relation.nspname, protected_relation.relname);
            probe_succeeded := true;
        EXCEPTION WHEN insufficient_privilege THEN
            NULL;
        END;
        IF probe_succeeded THEN
            RAISE EXCEPTION 'Negative authorized-select probe unexpectedly succeeded';
        END IF;
    END LOOP;
END
$verify$;

SELECT check_name, severity FROM ax.monitor_health_check() ORDER BY check_name LIMIT 200;
SELECT pgt_schema, pgt_name, stale FROM pgtrickle.stream_tables_info
 WHERE pgt_schema = 'ax' ORDER BY pgt_name LIMIT 20;
SELECT tenant_id, orders, seed_orders FROM ax.tenant_order_counts() ORDER BY tenant_id LIMIT 100;
ROLLBACK;
