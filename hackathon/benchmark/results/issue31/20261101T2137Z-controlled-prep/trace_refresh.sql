-- PREPARED ONLY. One psql backend/transaction through refresh and temp reads.
-- Variables: stream, experiment=(primary_default|comparison_fast_off_merge|
-- comparison_fast_off_auto), case_id. Never use on a preserved database.
\set ON_ERROR_STOP on
SELECT current_database()='ax_g4_repro' AND current_setting('pg_trickle.enabled',true)='off'
 AND :'stream' IN ('st_day_product_status','st_day_category_status','st_hour_category_status')
 AND :'experiment' IN ('primary_default','comparison_fast_off_merge','comparison_fast_off_auto')
 AND :'case_id' IN ('A','B_update') AS allowed \gset
\if :allowed
\else
  \quit 3
\endif
BEGIN;
SET LOCAL statement_timeout='5s';
SET LOCAL lock_timeout='500ms';
SET LOCAL pg_trickle.log_delta_sql=on;
SET LOCAL pg_trickle.log_merge_sql=on;
SET LOCAL client_min_messages=debug1;
SET LOCAL log_min_messages=debug1;
-- Primary intentionally issues NO SET for aggregate_fast_path, merge_strategy,
-- or merge_strategy_threshold: preserve the installed v0.108.3 defaults.
SELECT :'experiment' <> 'primary_default' AS comparison_run \gset
\if :comparison_run
  SET LOCAL pg_trickle.aggregate_fast_path=off;
  SELECT set_config('pg_trickle.merge_strategy',
    CASE :'experiment' WHEN 'comparison_fast_off_merge' THEN 'merge' ELSE 'auto' END,true);
\endif
SELECT name,setting,reset_val,source FROM pg_settings
 WHERE name IN ('pg_trickle.aggregate_fast_path','pg_trickle.merge_strategy',
                'pg_trickle.merge_strategy_threshold') ORDER BY name;
SELECT pgt_id AS sid FROM pgtrickle.pgt_stream_tables
 WHERE pgt_schema='ax' AND pgt_name=:'stream' \gset
SELECT 'ax.orders'::regclass::oid AS source_oid \gset
SELECT coalesce(max(refresh_id),0) AS prior_refresh_id
 FROM pgtrickle.pgt_refresh_history WHERE pgt_id=:sid \gset
SELECT json_build_object('phase','before','utc',clock_timestamp(),'snapshot',txid_current_snapshot()::text,
 'frontier',frontier,'needs_reinit',needs_reinit,'status',status,
 'effective_refresh_mode',effective_refresh_mode,'is_populated',is_populated)
 FROM pgtrickle.pgt_stream_tables WHERE pgt_id=:sid;
SELECT count(*)=1 AND bool_and(source_stable_name IS NOT NULL) AS tracking_ok
 FROM pgtrickle.pgt_change_tracking WHERE source_relid=:source_oid \gset
\if :tracking_ok
\else
  \echo 'INCONCLUSIVE: source tracking metadata missing or ambiguous; no refresh attempted'
  ROLLBACK;
  \quit 4
\endif
SELECT format('CREATE TEMP TABLE raw_before ON COMMIT DROP AS SELECT * FROM pgtrickle_changes.%I WHERE action IN (''I'',''D'')',
 'changes_'||source_stable_name) FROM pgtrickle.pgt_change_tracking WHERE source_relid=:source_oid \gexec
SELECT json_agg(to_jsonb(r)-'__pgt_trace_context' ORDER BY change_id) FROM raw_before r;
SELECT pgtrickle.refresh_stream_table('ax.'||:'stream');
SELECT json_build_object('phase','after','utc',clock_timestamp(),'snapshot',txid_current_snapshot()::text,
 'frontier',frontier,'effective_mode',effective_refresh_mode,'status',status,
 'needs_reinit',needs_reinit) FROM pgtrickle.pgt_stream_tables WHERE pgt_id=:sid;
SELECT format('pg_temp.__pgt_cdc_%s_%s',:sid,:source_oid) AS stage_name,
       format('pg_temp.__pgt_delta_%s',:sid) AS delta_name \gset
SELECT to_regclass(:'stage_name') IS NOT NULL AS stage_present,
       to_regclass(:'delta_name') IS NOT NULL AS delta_present \gset
\if :stage_present
  SELECT format('SELECT json_agg(to_jsonb(s) ORDER BY change_id) FROM %s s',to_regclass(:'stage_name')) \gexec
\else
  \echo 'STAGING_TRACE INCONCLUSIVE: internal post-stage relation absent or not inspectable'
\endif
\if :delta_present
  SELECT format('SELECT json_agg(to_jsonb(d)) FROM %s d',to_regclass(:'delta_name')) \gexec
\else
  \echo 'AGGREGATE_DELTA_TRACE INCONCLUSIVE: selected path may not materialize this relation; SQL logs are not row evidence'
\endif
SELECT refresh_id,start_time,end_time,action,status,initiated_by,delta_row_count,
 merge_strategy_used,was_full_fallback,refresh_reason
 FROM pgtrickle.pgt_refresh_history
 WHERE pgt_id=:sid AND refresh_id>:prior_refresh_id ORDER BY refresh_id;
SELECT json_build_object(
 'case_id',:'case_id','requested_experiment',:'experiment',
 'stage_observed',:stage_present,'materialized_delta_observed',:delta_present,
 'runtime_verdict','INCONCLUSIVE_UNLESS_ALL_STAGE_PRODUCER_APPLY_AND_ORACLE_EVIDENCE_EXISTS');
SELECT format('SELECT json_agg(to_jsonb(t)) FROM ax.%I t WHERE tenant_id=1 AND utc_day IN (''2026-11-20'',''2026-11-21'')',:'stream')
 WHERE :'stream'<>'st_hour_category_status' \gexec
SELECT json_agg(to_jsonb(t)) FROM ax.st_hour_category_status t
 WHERE tenant_id=1 AND utc_hour>='2026-11-20' AND utc_hour<'2026-11-22';
COMMIT;
-- Do not replay resolved delta SQL after applying it: it reads changed target state.
-- pg_temp.__pgt_cdc_* is post-reducer/post-visibility only; raw_before is a
-- pre-stage buffer copy. These do not expose both intermediate boundaries.
-- Capture actual apply selection from this refresh's history row, not the
-- requested GUCs. If the row, producer, boundaries, or oracle is unavailable,
-- verdict stays INCONCLUSIVE. logs/template text and temp-table absence are not proof.
-- Preserve bounded container stderr/log output externally, correlated by PID,
-- pgt_id, case_id and interval. The DELTA SQL message is diagnostic SQL text;
-- require explicit vector execution evidence where applicable. If producer
-- (P5 vs standard vs vector) is ambiguous, record unknown/INCONCLUSIVE.
