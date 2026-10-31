\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '10s';
SET LOCAL search_path = pg_catalog, pg_temp;

DO $deployment_blocked$
BEGIN
    RAISE EXCEPTION 'DEPLOYMENT BLOCKED: installed binary provenance, live ACL baseline and disposable security validation are not verified. Remove this hold only in a separately reviewed, explicitly authorized revision.';
END
$deployment_blocked$;

SET LOCAL ax.monitor_health_phase = 'before';
\ir 003_monitor_health_guards.sql

CREATE ROLE ax_health_owner NOLOGIN NOSUPERUSER NOBYPASSRLS
    NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT;
GRANT pg_read_all_stats TO ax_health_owner WITH ADMIN FALSE, INHERIT TRUE, SET FALSE;
GRANT USAGE ON SCHEMA pgtrickle, pgtrickle_changes TO ax_health_owner;
GRANT SELECT (pgt_id, pgt_schema, pgt_name, pgt_relid, status, refresh_reason,
    refresh_reason_detail, needs_reinit, consecutive_errors, refresh_mode,
    downstream_publication_name, target_freshness_mode, freshness_deadline_ms)
    ON TABLE pgtrickle.pgt_stream_tables TO ax_health_owner;
GRANT SELECT (pgt_schema, pgt_name, stale)
    ON TABLE pgtrickle.stream_tables_info TO ax_health_owner;
GRANT SELECT (was_full_fallback, start_time)
    ON TABLE pgtrickle.pgt_refresh_history TO ax_health_owner;
GRANT SELECT (pgt_id, source_relid, source_type, columns_used, cdc_mode, slot_name,
    decoder_confirmed_lsn, transition_started_at, cutover_target, cutover_lsn,
    column_snapshot, schema_fingerprint, source_stable_name, source_placement)
    ON TABLE pgtrickle.pgt_dependencies TO ax_health_owner;
GRANT SELECT (source_relid, source_stable_name, slot_name)
    ON TABLE pgtrickle.pgt_change_tracking TO ax_health_owner;
GRANT SELECT (pgt_id, node_ordinal, spec_ordinal, status, estimated_bytes)
    ON TABLE pgtrickle.pgt_window_states TO ax_health_owner;
GRANT SELECT (stream_table_oid, tide_outbox_name)
    ON TABLE pgtrickle.pgt_outbox_config TO ax_health_owner;
GRANT SELECT (status)
    ON TABLE pgtrickle.pgt_scheduler_jobs TO ax_health_owner;
GRANT SELECT (pgt_id, sla_status, p95_freshness_ms)
    ON TABLE pgtrickle.pgt_freshness_controller_state TO ax_health_owner;
GRANT SELECT (pgt_id, stream_relid, publication_oid, publication_name,
    publication_owner_oid, expected_relation_oids)
    ON TABLE pgtrickle.pgt_publication_bindings TO ax_health_owner;
GRANT EXECUTE ON FUNCTION pgtrickle.health_check(), pgtrickle.change_buffer_sizes(),
    pgtrickle.slot_health(), pgtrickle.parse_duration_seconds(text) TO ax_health_owner;

\ir 003_monitor_health_function.sql
REVOKE ALL ON FUNCTION ax.monitor_health_check() FROM PUBLIC;
ALTER FUNCTION ax.monitor_health_check() OWNER TO ax_health_owner;
GRANT EXECUTE ON FUNCTION ax.monitor_health_check() TO ax_monitor;

SET LOCAL ax.monitor_health_phase = 'after';
\ir 003_monitor_health_guards.sql
COMMIT;
