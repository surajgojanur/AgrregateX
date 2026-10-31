-- PREPARED ONLY. Keep ONE connection/transaction through refresh and temp-table reads.
-- Variables: stream = one original stream name, strategy = merge or auto.
-- Never call on a preserved database. Missing temp evidence is a blocker, not a PASS.
\set ON_ERROR_STOP on
SELECT current_database()='ax_g4_repro' AND current_setting('pg_trickle.enabled',true)='off'
 AND :'stream' IN ('st_day_product_status','st_day_category_status','st_hour_category_status')
 AND :'strategy' IN ('merge','auto') AS allowed \gset
\if :allowed
\else
  \quit 3
\endif
BEGIN;
SET LOCAL statement_timeout='5s';
SET LOCAL lock_timeout='500ms';
SET LOCAL pg_trickle.log_delta_sql=on;
SET LOCAL pg_trickle.log_merge_sql=on;
SET LOCAL pg_trickle.aggregate_fast_path=off;
SET LOCAL log_min_messages=debug1;
SELECT set_config('pg_trickle.merge_strategy',:'strategy',true);
SET LOCAL pg_trickle.merge_strategy_threshold=1.0;
SELECT pgt_id AS sid FROM pgtrickle.pgt_stream_tables
 WHERE pgt_schema='ax' AND pgt_name=:'stream' \gset
SELECT 'ax.orders'::regclass::oid AS source_oid \gset
SELECT json_build_object('phase','before','utc',clock_timestamp(),'snapshot',txid_current_snapshot()::text,
 'frontier',frontier,'needs_reinit',needs_reinit) FROM pgtrickle.pgt_stream_tables WHERE pgt_id=:sid;
SELECT format('CREATE TEMP TABLE raw_before ON COMMIT DROP AS SELECT * FROM pgtrickle_changes.%I WHERE action IN (''I'',''D'')',
 'changes_'||source_stable_name) FROM pgtrickle.pgt_change_tracking WHERE source_relid=:source_oid \gexec
SELECT json_agg(to_jsonb(r)-'__pgt_trace_context' ORDER BY change_id) FROM raw_before r;
SELECT pgtrickle.refresh_stream_table('ax.'||:'stream');
SELECT json_build_object('phase','after','utc',clock_timestamp(),'snapshot',txid_current_snapshot()::text,
 'frontier',frontier,'effective_mode',effective_refresh_mode) FROM pgtrickle.pgt_stream_tables WHERE pgt_id=:sid;
SELECT format('pg_temp.__pgt_cdc_%s_%s',:sid,:source_oid) AS stage_name,
       format('pg_temp.__pgt_delta_%s',:sid) AS delta_name \gset
SELECT to_regclass(:'stage_name') IS NOT NULL AS stage_present,
       to_regclass(:'delta_name') IS NOT NULL AS delta_present \gset
\if :stage_present
  SELECT format('SELECT json_agg(to_jsonb(s)-''__pgt_trace_context'' ORDER BY change_id) FROM %s s',to_regclass(:'stage_name')) \gexec
\else
  \echo 'STAGING_TRACE BLOCKED: internal stage absent; stop internal-trace subtask'
  ROLLBACK;
  \quit 4
\endif
\if :delta_present
  SELECT format('SELECT json_agg(to_jsonb(d)) FROM %s d',to_regclass(:'delta_name')) \gexec
\else
  \echo 'AGGREGATE_DELTA_TRACE BLOCKED: no materialized delta; SQL logging alone is not row evidence'
  ROLLBACK;
  \quit 4
\endif
SELECT refresh_id,start_time,end_time,action,status,delta_row_count,merge_strategy_used,
 was_full_fallback,refresh_reason FROM pgtrickle.pgt_refresh_history
 WHERE pgt_id=:sid ORDER BY refresh_id DESC LIMIT 3;
SELECT format('SELECT json_agg(to_jsonb(t)) FROM ax.%I t WHERE tenant_id=1 AND utc_day IN (''2026-11-20'',''2026-11-21'')',:'stream')
 WHERE :'stream'<>'st_hour_category_status' \gexec
SELECT json_agg(to_jsonb(t)) FROM ax.st_hour_category_status t
 WHERE tenant_id=1 AND utc_hour>='2026-11-20' AND utc_hour<'2026-11-22';
COMMIT;
-- Do not replay resolved delta SQL after applying it: it reads changed target state.
-- Retain raw_before output externally and filter by exact observed before/after LSNs.
