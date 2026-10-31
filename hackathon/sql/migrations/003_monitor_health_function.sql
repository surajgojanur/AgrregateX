\set ON_ERROR_STOP on
-- REVIEW ONLY: migration 003 is NOT APPLIED and has no deployment approval.
-- This independent hold also blocks standalone includes and diagnostic scripts.
DO $review_only_hold$
BEGIN
    RAISE EXCEPTION 'DEPLOYMENT APPROVAL HOLD: migration 003 requires separate reviewed authorization; do not execute this proposal or its includes.';
END
$review_only_hold$;

CREATE FUNCTION ax.monitor_health_check()
RETURNS TABLE (check_name text, severity text, detail text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
SET row_security = on
AS $monitor_health$
DECLARE
    missing_count integer;
    report jsonb;
    required_checks text[] := ARRAY[
        'scheduler_running', 'error_tables', 'stale_tables', 'needs_reinit',
        'consecutive_errors', 'buffer_growth', 'slot_lag', 'attachment_owner_check',
        'dvm_fallbacks', 'ring_overflow_trend', 'immediate_ivm_triggers',
        'publication_bindings', 'freshness_evidence', 'freshness_breach',
        'freshness_infeasible', 'freshness_override', 'adaptive_workers',
        'memory_budget', 'scheduler_load', 'disk_forecast'
    ];
BEGIN
    IF session_user <> 'ax_monitor' OR current_user <> 'ax_health_owner' THEN
        RAISE EXCEPTION USING ERRCODE = '42501',
            MESSAGE = 'Health diagnostics require the actual ax_monitor login and isolated owner';
    END IF;
    IF current_database() <> 'aggregatex'
       OR current_setting('server_version_num')::integer <> 180006
       OR NOT EXISTS (SELECT 1 FROM pg_extension
                       WHERE extname = 'pg_trickle' AND extversion = '0.108.3')
       OR current_setting('pg_trickle.change_buffer_schema', true)
          IS DISTINCT FROM 'pgtrickle_changes'
       OR current_setting('pg_trickle.parallel_refresh_mode', true) IS NULL
       OR current_setting('pg_trickle.disk_headroom_mb', true) IS NULL
    THEN
        RETURN QUERY SELECT 'monitor_contract', 'UNKNOWN',
            'Unreviewed database, engine version or diagnostic configuration'::text;
        RETURN;
    END IF;

    WITH required(relation_name, columns) AS (
        VALUES
        ('pgt_stream_tables', ARRAY['pgt_id', 'pgt_schema', 'pgt_name', 'pgt_relid',
            'status', 'refresh_reason', 'refresh_reason_detail', 'needs_reinit',
            'consecutive_errors', 'refresh_mode', 'downstream_publication_name',
            'target_freshness_mode', 'freshness_deadline_ms']),
        ('stream_tables_info', ARRAY['pgt_schema', 'pgt_name', 'stale']),
        ('pgt_refresh_history', ARRAY['was_full_fallback', 'start_time']),
        ('pgt_dependencies', ARRAY['pgt_id', 'source_relid', 'source_type',
            'columns_used', 'cdc_mode', 'slot_name', 'decoder_confirmed_lsn',
            'transition_started_at', 'cutover_target', 'cutover_lsn',
            'column_snapshot', 'schema_fingerprint', 'source_stable_name', 'source_placement']),
        ('pgt_change_tracking', ARRAY['source_relid', 'source_stable_name', 'slot_name']),
        ('pgt_window_states', ARRAY['pgt_id', 'node_ordinal', 'spec_ordinal', 'status', 'estimated_bytes']),
        ('pgt_outbox_config', ARRAY['stream_table_oid', 'tide_outbox_name']),
        ('pgt_scheduler_jobs', ARRAY['status']),
        ('pgt_freshness_controller_state', ARRAY['pgt_id', 'sla_status', 'p95_freshness_ms']),
        ('pgt_publication_bindings', ARRAY['pgt_id', 'stream_relid', 'publication_oid',
            'publication_name', 'publication_owner_oid', 'expected_relation_oids'])
    )
    SELECT count(*) INTO missing_count
      FROM required
      CROSS JOIN LATERAL unnest(required.columns) AS needed(column_name)
      LEFT JOIN pg_namespace namespace ON namespace.nspname = 'pgtrickle'
      LEFT JOIN pg_class relation ON relation.relnamespace = namespace.oid
                                AND relation.relname = required.relation_name
      LEFT JOIN pg_attribute attribute ON attribute.attrelid = relation.oid
             AND attribute.attname = needed.column_name AND attribute.attnum > 0
             AND NOT attribute.attisdropped
     WHERE attribute.attnum IS NULL
        OR NOT has_column_privilege(current_user, relation.oid, attribute.attnum, 'SELECT');

    IF missing_count <> 0
       OR NOT has_schema_privilege(current_user, 'pgtrickle', 'USAGE')
       OR NOT has_schema_privilege(current_user, 'pgtrickle_changes', 'USAGE')
       OR NOT pg_has_role(current_user, 'pg_read_all_stats', 'USAGE')
       OR EXISTS (
           SELECT 1 FROM (VALUES
               ('pgtrickle.health_check()'), ('pgtrickle.change_buffer_sizes()'),
               ('pgtrickle.slot_health()'), ('pgtrickle.parse_duration_seconds(text)'),
               ('pg_catalog.pg_current_wal_lsn()'), ('pg_catalog.to_regclass(text)'),
               ('pg_catalog.pg_total_relation_size(regclass)'),
               ('pg_catalog.pg_size_pretty(bigint)')
           ) AS required(signature)
           WHERE to_regprocedure(required.signature) IS NULL
              OR NOT has_function_privilege(current_user, to_regprocedure(required.signature), 'EXECUTE')
       )
    THEN
        RETURN QUERY SELECT 'monitor_contract', 'UNKNOWN',
            'Required diagnostic catalog, schema, function or statistics privilege is missing'::text;
        RETURN;
    END IF;

    IF current_setting('pg_trickle.parallel_refresh_mode') <> 'off' THEN
        required_checks := required_checks || ARRAY['worker_pool', 'job_queue'];
    END IF;
    SELECT required_checks || COALESCE(array_agg(expected.name), ARRAY[]::text[])
      INTO required_checks
      FROM (
          SELECT 'freshness_sla_' || stream.pgt_id AS name
            FROM pgtrickle.pgt_stream_tables stream
           WHERE stream.target_freshness_mode = 'INTERVAL'
          UNION ALL
          SELECT 'schema_evolution_' || stream.pgt_id
            FROM pgtrickle.pgt_stream_tables stream
           WHERE stream.status = 'SUSPENDED' AND stream.refresh_reason LIKE 'SOURCE_%'
          UNION ALL
          SELECT 'window_state_' || state.pgt_id || '_' || state.node_ordinal || '_' || state.spec_ordinal
            FROM pgtrickle.pgt_window_states state WHERE state.status <> 'READY'
      ) AS expected;

    SELECT COALESCE(jsonb_agg(to_jsonb(health)), '[]'::jsonb) INTO report
      FROM pgtrickle.health_check() AS health;
    RETURN QUERY
        SELECT result.check_name, result.severity, result.detail
          FROM jsonb_to_recordset(report) AS result(check_name text, severity text, detail text);
    IF EXISTS (
        SELECT 1 FROM unnest(required_checks) AS expected(name)
         WHERE NOT EXISTS (SELECT 1 FROM jsonb_array_elements(report) AS result(value)
                            WHERE result.value->>'check_name' = expected.name)
    ) OR EXISTS (
        SELECT 1 FROM jsonb_array_elements(report) AS result(value)
         WHERE result.value->>'severity' IS NULL
            OR result.value->>'severity' NOT IN ('OK', 'WARN', 'WARNING', 'ERROR')
            OR result.value->>'detail' IS NULL
    ) OR EXISTS (
        SELECT 1 FROM jsonb_array_elements(report) AS result(value)
         GROUP BY result.value->>'check_name' HAVING count(*) <> 1
    ) THEN
        RETURN QUERY SELECT 'monitor_contract', 'UNKNOWN',
            'Incomplete health evidence; a required check is missing or malformed'::text;
    ELSE
        RETURN QUERY SELECT 'monitor_contract', 'OK',
            'Required privileges and applicable health-check coverage verified'::text;
    END IF;
EXCEPTION
    WHEN insufficient_privilege OR undefined_table OR undefined_column OR undefined_function THEN
        IF session_user <> 'ax_monitor' OR current_user <> 'ax_health_owner' THEN
            RAISE;
        END IF;
        RETURN QUERY SELECT 'monitor_contract', 'UNKNOWN',
            ('Diagnostic dependency unavailable (SQLSTATE ' || SQLSTATE || ')')::text;
END
$monitor_health$;
