BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='2s'; SET LOCAL lock_timeout='500ms';
SELECT json_build_object('utc',clock_timestamp() AT TIME ZONE 'UTC','snapshot',txid_current_snapshot()::text);
SELECT json_agg(r) FROM (SELECT s.pgt_name,h.action,h.status,h.was_full_fallback,h.refresh_reason,count(*) n,
min(h.start_time) first_start,max(h.end_time) last_end FROM pgtrickle.pgt_refresh_history h
JOIN pgtrickle.pgt_stream_tables s USING(pgt_id) WHERE s.pgt_schema='ax' GROUP BY 1,2,3,4,5 ORDER BY 1,2)r;
SELECT json_agg(r) FROM (SELECT refresh_id,start_time,end_time,action,status,rows_inserted,rows_updated,rows_deleted,
delta_row_count,was_full_fallback,refresh_reason,merge_strategy_used,initiated_by FROM pgtrickle.pgt_refresh_history
WHERE pgt_id=1 AND action<>'NO_DATA' ORDER BY refresh_id DESC LIMIT 20)r;
SELECT json_agg(r) FROM (SELECT refresh_id,start_time,end_time,action,status FROM pgtrickle.pgt_refresh_history
WHERE pgt_id=1 ORDER BY refresh_id DESC LIMIT 5)r;
SELECT json_agg(r) FROM (SELECT source_relid::regclass::text source,cdc_mode,pgt_id FROM pgtrickle.pgt_dependencies ORDER BY pgt_id,source_relid)r;
SELECT json_agg(r) FROM (SELECT source_relid::regclass::text source,last_consumed_lsn,receipt_high_water_lsn,
acknowledged_high_water_lsn,tracked_by_pgt_ids FROM pgtrickle.pgt_change_tracking ORDER BY source_relid)r;
SELECT json_build_object('orders_buffer_rows',count(*),'oldest_commit',min(source_commit_at),'newest_commit',max(source_commit_at))
FROM pgtrickle_changes.changes_daaaeeb1fdc57e97;
SELECT json_build_object('products_buffer_rows',count(*)) FROM pgtrickle_changes.changes_1d8a10d0e8bcdd15;
SELECT json_agg(r) FROM (SELECT backend_type,state,wait_event_type,wait_event,count(*) n
FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid()
GROUP BY 1,2,3,4 ORDER BY 1,2)r;
SELECT json_agg(r) FROM (SELECT name,setting FROM pg_settings WHERE name IN
('pg_trickle.enabled','pg_trickle.scheduler_interval_ms','pg_trickle.max_concurrent_refreshes') ORDER BY name)r;
ROLLBACK;
