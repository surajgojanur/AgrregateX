-- Issue #34: narrow monitor-only SELECT on pg_trickle's health-check metadata view.
-- Existing Fedora aggregatex/round1 repair ONLY; NOT automatically run during deploy.
-- This transaction does not modify source rows, RLS, schemas, extension objects, or roles.
-- Inspect 002_monitor_health_view_verify.sql and the runbook before human-approved apply.
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '10s';

DO $guard$
DECLARE
    v oid;
    view_owner oid;
    view_kind "char";
    view_options text[];
    expected_base oid;
    monitor_oid oid;
BEGIN
    -- Fail closed if accidentally pointed at the wrong database, owner, or extension.
    IF current_database() <> 'aggregatex'
       OR current_user <> 'postgres'
       OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = current_user AND rolsuper)
    THEN
        RAISE EXCEPTION 'Wrong database or untrusted migration role (expected aggregatex/postgres superuser)';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_extension
         WHERE extname = 'pg_trickle' AND extversion = '0.108.3'
    ) THEN
        RAISE EXCEPTION 'Unknown pg_trickle extension version; inspect installed view before changing ACL';
    END IF;

    SELECT c.oid, c.relowner, c.relkind, c.reloptions
      INTO v, view_owner, view_kind, view_options
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'pgtrickle' AND c.relname = 'stream_tables_info';
    IF v IS NULL OR view_kind <> 'v' OR view_owner <> (SELECT oid FROM pg_roles WHERE rolname=current_user)
       OR 'security_invoker=true' = ANY(COALESCE(view_options, ARRAY[]::text[]))
    THEN
        RAISE EXCEPTION 'Unexpected stream_tables_info view type, owner, or security options';
    END IF;
    -- The observed view comes only from pgtrickle.pgt_stream_tables, NOT tenant data.
    SELECT 'pgtrickle.pgt_stream_tables'::regclass::oid INTO expected_base;
    IF NOT EXISTS (
         SELECT 1 FROM pg_rewrite rw JOIN pg_depend d
           ON d.classid = 'pg_rewrite'::regclass AND d.objid = rw.oid
          AND d.refclassid = 'pg_class'::regclass
         WHERE rw.ev_class = v AND rw.rulename = '_RETURN'
           AND d.refobjid = expected_base
    ) OR EXISTS (
         SELECT 1 FROM pg_rewrite rw JOIN pg_depend d
           ON d.classid = 'pg_rewrite'::regclass AND d.objid = rw.oid
          AND d.refclassid = 'pg_class'::regclass
         WHERE rw.ev_class = v AND rw.rulename = '_RETURN'
           AND d.refobjid NOT IN (v, expected_base)
    ) THEN
        RAISE EXCEPTION 'View dependencies differ from verified catalog-only definition';
    END IF;
    IF (SELECT count(*) FROM pg_attribute
         WHERE attrelid = v AND attname IN ('pgt_schema', 'pgt_name', 'stale')
           AND attnum > 0 AND NOT attisdropped) <> 3 THEN
        RAISE EXCEPTION 'Health-check view does not have expected metadata columns';
    END IF;

    SELECT oid INTO monitor_oid FROM pg_roles
     WHERE rolname = 'ax_monitor' AND rolcanlogin
       AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreatedb AND NOT rolcreaterole;
    IF monitor_oid IS NULL OR NOT has_schema_privilege('ax_monitor','pgtrickle','USAGE')
       OR NOT has_table_privilege('ax_monitor','pgtrickle.pgt_stream_tables','SELECT')
       OR NOT has_function_privilege('ax_monitor','pgtrickle.health_check()','EXECUTE')
       OR has_table_privilege('ax_monitor','ax.orders','SELECT')
       OR has_table_privilege('ax_monitor','ax.products','SELECT')
    THEN
        RAISE EXCEPTION 'Unexpected monitor role or access; refuse privilege change';
    END IF;
END
$guard$;

-- The only intended permission change. Idempotent and transaction-scoped.
GRANT SELECT ON TABLE pgtrickle.stream_tables_info TO ax_monitor;

DO $verify$
BEGIN
    IF NOT has_table_privilege('ax_monitor','pgtrickle.stream_tables_info','SELECT')
       OR has_table_privilege('ax_monitor','ax.orders','SELECT')
       OR has_table_privilege('ax_monitor','ax.products','SELECT')
       OR has_table_privilege('ax_monitor','pgtrickle.stream_tables_info','INSERT')
       OR has_table_privilege('ax_monitor','pgtrickle.stream_tables_info','UPDATE')
       OR has_table_privilege('ax_monitor','pgtrickle.stream_tables_info','DELETE')
    THEN
        RAISE EXCEPTION 'Post-grant privilege verification failed: rolling back';
    END IF;
END
$verify$;
COMMIT;
