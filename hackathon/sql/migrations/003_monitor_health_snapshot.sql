\set ON_ERROR_STOP on
-- REVIEW ONLY: migration 003 is NOT APPLIED and has no deployment approval.
-- This independent hold also blocks standalone includes and diagnostic scripts.
DO $review_only_hold$
BEGIN
    RAISE EXCEPTION 'DEPLOYMENT APPROVAL HOLD: migration 003 requires separate reviewed authorization; do not execute this proposal or its includes.';
END
$review_only_hold$;

BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '2s';
SET LOCAL lock_timeout = '1s';
SET LOCAL idle_in_transaction_session_timeout = '15s';
SET LOCAL search_path = pg_catalog, pg_temp;

DO $target$
BEGIN
    IF current_database() <> 'aggregatex' OR session_user <> 'postgres' OR current_user <> session_user
       OR current_setting('server_version_num')::integer <> 180006
       OR NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trickle' AND extversion = '0.108.3') THEN
        RAISE EXCEPTION 'Verify container/port identity out of band; expected aggregatex/postgres, PG 18.6, pg_trickle 0.108.3';
    END IF;
END
$target$;

SELECT current_database() AS database_name, session_user AS login,
       current_setting('server_version_num') AS server_version_num,
       extension.extversion, pg_get_userbyid(extension.extowner) AS extension_owner,
       pg_get_userbyid(database.datdba) AS database_owner
  FROM pg_extension extension JOIN pg_database database ON database.datname = current_database()
 WHERE extension.extname = 'pg_trickle';

SELECT rolname, rolcanlogin, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole, rolreplication, rolinherit
  FROM pg_roles WHERE rolname IN ('postgres', 'ax_monitor', 'ax_api', 'ax_writer', 'ax_health_owner') ORDER BY rolname;
SELECT member.rolname AS member, granted.rolname AS granted_role,
       membership.admin_option, membership.inherit_option, membership.set_option
  FROM pg_auth_members membership JOIN pg_roles member ON member.oid = membership.member
  JOIN pg_roles granted ON granted.oid = membership.roleid
 WHERE member.rolname IN ('ax_monitor', 'ax_api', 'ax_writer', 'ax_health_owner') ORDER BY 1, 2 LIMIT 50;

SELECT namespace.nspname, relation.relname, pg_get_userbyid(relation.relowner) AS owner,
       relation.relkind, relation.relrowsecurity, relation.relforcerowsecurity,
       has_table_privilege('ax_monitor', relation.oid, 'SELECT') AS monitor_table_select,
       has_any_column_privilege('ax_monitor', relation.oid, 'SELECT') AS monitor_any_column_select,
       has_any_column_privilege('ax_api', relation.oid, 'SELECT') AS api_any_column_select,
       has_any_column_privilege('ax_writer', relation.oid, 'SELECT') AS writer_any_column_select
  FROM pg_class relation JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
 WHERE (namespace.nspname = 'pgtrickle' AND relation.relname IN (
       'pgt_stream_tables', 'stream_tables_info', 'pgt_refresh_history', 'pgt_dependencies',
       'pgt_change_tracking', 'pgt_window_states', 'pgt_outbox_config', 'pgt_scheduler_jobs',
       'pgt_freshness_controller_state', 'pgt_publication_bindings'))
    OR (namespace.nspname = 'ax' AND relation.relname IN ('orders', 'products',
       'st_day_product_status', 'st_day_category_status', 'st_hour_category_status'))
 ORDER BY 1, 2;

SELECT relation.relname, attribute.attname,
       has_column_privilege('ax_monitor', relation.oid, attribute.attnum, 'SELECT') AS monitor_select,
       CASE WHEN diagnostic.oid IS NOT NULL
            THEN has_column_privilege(diagnostic.oid, relation.oid, attribute.attnum, 'SELECT') END AS isolated_owner_select
  FROM pg_class relation JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
  JOIN pg_attribute attribute ON attribute.attrelid = relation.oid AND attribute.attnum > 0 AND NOT attribute.attisdropped
  LEFT JOIN pg_roles diagnostic ON diagnostic.rolname = 'ax_health_owner'
 WHERE namespace.nspname = 'pgtrickle' AND relation.relname IN (
       'pgt_dependencies', 'pgt_change_tracking', 'pgt_window_states', 'pgt_outbox_config',
       'pgt_scheduler_jobs', 'pgt_freshness_controller_state', 'pgt_publication_bindings')
 ORDER BY relation.relname, attribute.attnum LIMIT 200;

SELECT namespace.nspname,
       has_schema_privilege('ax_monitor', namespace.oid, 'USAGE') AS monitor_usage,
       has_schema_privilege('ax_monitor', namespace.oid, 'CREATE') AS monitor_create,
       has_schema_privilege('ax_api', namespace.oid, 'USAGE') AS api_usage,
       has_schema_privilege('ax_writer', namespace.oid, 'USAGE') AS writer_usage
  FROM pg_namespace namespace WHERE namespace.nspname IN ('ax', 'pgtrickle', 'pgtrickle_changes') ORDER BY 1;

SELECT procedure.proname, language.lanname, pg_get_userbyid(procedure.proowner) AS owner,
       procedure.prosecdef, procedure.provolatile, procedure.proconfig,
       md5(procedure.prosrc) AS body_fingerprint,
       CASE WHEN language.lanname = 'c' THEN procedure.probin END AS library_reference,
       has_function_privilege('ax_monitor', procedure.oid, 'EXECUTE') AS monitor_execute
  FROM pg_proc procedure JOIN pg_namespace namespace ON namespace.oid = procedure.pronamespace
  JOIN pg_language language ON language.oid = procedure.prolang
 WHERE (namespace.nspname = 'pgtrickle' AND procedure.proname IN (
       'health_check', 'slot_health', 'change_buffer_sizes', 'parse_duration_seconds'))
    OR (namespace.nspname = 'ax' AND procedure.proname IN ('monitor_health_check', 'tenant_order_counts'))
 ORDER BY 1 LIMIT 20;
SELECT md5(regexp_replace(pg_get_viewdef('pgtrickle.stream_tables_info'::regclass, true), '\s+', '', 'g')) AS stale_view_fingerprint;
SELECT count(*) AS private_executable_definer_functions
  FROM pg_proc procedure JOIN pg_namespace namespace ON namespace.oid = procedure.pronamespace
 WHERE namespace.nspname = 'pgtrickle_changes' AND procedure.prosecdef
   AND has_function_privilege('ax_monitor', procedure.oid, 'EXECUTE');

SELECT stream.pgt_schema, stream.pgt_name, stream.status, stream.schedule,
       stream.refresh_mode, stream.effective_refresh_mode, stream.refresh_tier,
       stream.last_refresh_at, stream.data_timestamp, stream.consecutive_errors,
       stream.last_error_code, stream.last_error_at,
       stream.last_error_message IS NOT NULL AS has_last_error,
       md5(stream.last_error_message) AS last_error_fingerprint,
       info.stale,
       extract(epoch FROM clock_timestamp() - stream.last_refresh_at) AS refresh_age_seconds,
       completed.end_time AS last_successful_refresh, completed.action AS last_successful_action
  FROM pgtrickle.pgt_stream_tables stream
  JOIN pgtrickle.stream_tables_info info USING (pgt_id)
  LEFT JOIN LATERAL (
      SELECT history.end_time, history.action FROM pgtrickle.pgt_refresh_history history
       WHERE history.pgt_id = stream.pgt_id AND history.status = 'COMPLETED'
       ORDER BY history.refresh_id DESC LIMIT 1
  ) completed ON true
 WHERE stream.pgt_schema = 'ax' ORDER BY stream.pgt_name LIMIT 20;

SELECT stream.pgt_name, history.start_time, history.end_time, history.action, history.status,
       history.error_code, history.error_sqlstate, history.was_full_fallback,
       history.error_message IS NOT NULL AS has_error, md5(history.error_message) AS error_fingerprint
  FROM pgtrickle.pgt_stream_tables stream
  CROSS JOIN LATERAL (
      SELECT start_time, end_time, action, status, error_code, error_sqlstate, was_full_fallback, error_message
        FROM pgtrickle.pgt_refresh_history history WHERE history.pgt_id = stream.pgt_id
       ORDER BY history.refresh_id DESC LIMIT 5
  ) history
 WHERE stream.pgt_schema = 'ax' ORDER BY stream.pgt_name, history.start_time DESC LIMIT 100;
SELECT backend_type, count(*) FROM pg_stat_activity
 WHERE backend_type IN ('pg_trickle launcher', 'pg_trickle scheduler')
   AND (datname = current_database() OR backend_type = 'pg_trickle launcher') GROUP BY backend_type;
SELECT name, setting FROM pg_settings WHERE name IN (
    'pg_trickle.enabled', 'pg_trickle.scheduler_interval_ms', 'pg_trickle.min_schedule_seconds',
    'pg_trickle.parallel_refresh_mode', 'pg_trickle.tiered_scheduling', 'pg_trickle.disk_headroom_mb',
    'pg_trickle.load_shed_threshold', 'pg_trickle.change_buffer_schema') ORDER BY name;
SELECT status, count(*) FROM pgtrickle.pgt_scheduler_jobs GROUP BY status ORDER BY status;
SELECT count(*) AS buffers, COALESCE(sum(pending_rows), 0) AS estimated_pending_rows,
       COALESCE(sum(buffer_bytes), 0) AS accounted_bytes FROM pgtrickle.change_buffer_sizes();
SELECT check_name, severity FROM pgtrickle.health_check() ORDER BY check_name LIMIT 200;
SELECT tenant_id, orders, seed_orders FROM ax.tenant_order_counts() ORDER BY tenant_id LIMIT 100;
ROLLBACK;
