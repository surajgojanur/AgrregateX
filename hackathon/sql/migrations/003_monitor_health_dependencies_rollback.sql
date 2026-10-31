\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '10s';
SET LOCAL search_path = pg_catalog, pg_temp;

DO $rollback_blocked$
BEGIN
    RAISE EXCEPTION 'ROLLBACK BLOCKED: requires separate approval and the recorded BEFORE snapshot proving that migration 003 created this role and function. Never remove pre-existing or drifted objects.';
END
$rollback_blocked$;

SET LOCAL ax.monitor_health_phase = 'rollback_before';
\ir 003_monitor_health_guards.sql

DROP FUNCTION ax.monitor_health_check();
REVOKE SELECT (pgt_id, pgt_schema, pgt_name, pgt_relid, status, refresh_reason,
    refresh_reason_detail, needs_reinit, consecutive_errors, refresh_mode,
    downstream_publication_name, target_freshness_mode, freshness_deadline_ms)
    ON TABLE pgtrickle.pgt_stream_tables FROM ax_health_owner;
REVOKE SELECT (pgt_schema, pgt_name, stale)
    ON TABLE pgtrickle.stream_tables_info FROM ax_health_owner;
REVOKE SELECT (was_full_fallback, start_time)
    ON TABLE pgtrickle.pgt_refresh_history FROM ax_health_owner;
REVOKE SELECT (pgt_id, source_relid, source_type, columns_used, cdc_mode, slot_name,
    decoder_confirmed_lsn, transition_started_at, cutover_target, cutover_lsn,
    column_snapshot, schema_fingerprint, source_stable_name, source_placement)
    ON TABLE pgtrickle.pgt_dependencies FROM ax_health_owner;
REVOKE SELECT (source_relid, source_stable_name, slot_name)
    ON TABLE pgtrickle.pgt_change_tracking FROM ax_health_owner;
REVOKE SELECT (pgt_id, node_ordinal, spec_ordinal, status, estimated_bytes)
    ON TABLE pgtrickle.pgt_window_states FROM ax_health_owner;
REVOKE SELECT (stream_table_oid, tide_outbox_name)
    ON TABLE pgtrickle.pgt_outbox_config FROM ax_health_owner;
REVOKE SELECT (status)
    ON TABLE pgtrickle.pgt_scheduler_jobs FROM ax_health_owner;
REVOKE SELECT (pgt_id, sla_status, p95_freshness_ms)
    ON TABLE pgtrickle.pgt_freshness_controller_state FROM ax_health_owner;
REVOKE SELECT (pgt_id, stream_relid, publication_oid, publication_name,
    publication_owner_oid, expected_relation_oids)
    ON TABLE pgtrickle.pgt_publication_bindings FROM ax_health_owner;
REVOKE EXECUTE ON FUNCTION pgtrickle.health_check(), pgtrickle.change_buffer_sizes(),
    pgtrickle.slot_health(), pgtrickle.parse_duration_seconds(text) FROM ax_health_owner;
REVOKE USAGE ON SCHEMA pgtrickle, pgtrickle_changes FROM ax_health_owner;
REVOKE pg_read_all_stats FROM ax_health_owner;
DROP ROLE ax_health_owner;

SET LOCAL ax.monitor_health_phase = 'rollback_after';
\ir 003_monitor_health_guards.sql
COMMIT;
