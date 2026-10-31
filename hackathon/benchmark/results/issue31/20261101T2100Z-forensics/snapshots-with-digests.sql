BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='2s';
SET LOCAL lock_timeout='500ms';
SELECT json_build_object('observation_utc',clock_timestamp() AT TIME ZONE 'UTC','snapshot',txid_current_snapshot()::text,
'database',current_database(),'role',current_user,'server_version',current_setting('server_version'),
'extension',(SELECT extversion FROM pg_extension WHERE extname='pg_trickle'),
'timezone',current_setting('TimeZone'),'read_only',current_setting('transaction_read_only'),
'isolation',current_setting('transaction_isolation'),'orders',(SELECT count(*) FROM ax.orders));
SELECT json_agg(r) FROM (WITH
o_dps AS (
    SELECT o.tenant_id, date_trunc('day', o.created_at AT TIME ZONE 'UTC') AS utc_day,
           o.product_id, o.status, COUNT(*) AS order_count, SUM(o.quantity) AS units,
           SUM(o.quantity::bigint * o.unit_price_cents) AS sales_cents
    FROM ax.orders o GROUP BY 1, 2, 3, 4),
s_dps AS (
    SELECT tenant_id, utc_day, product_id, status, order_count, units, sales_cents
    FROM ax.st_day_product_status),
o_dcs AS (
    SELECT o.tenant_id, date_trunc('day', o.created_at AT TIME ZONE 'UTC') AS utc_day,
           p.category_id, o.status, COUNT(*) AS order_count, SUM(o.quantity) AS units,
           SUM(o.quantity::bigint * o.unit_price_cents) AS sales_cents
    FROM ax.orders o JOIN ax.products p USING (tenant_id, product_id) GROUP BY 1, 2, 3, 4),
s_dcs AS (
    SELECT tenant_id, utc_day, category_id, status, order_count, units, sales_cents
    FROM ax.st_day_category_status),
o_hcs AS (
    SELECT o.tenant_id, date_trunc('hour', o.created_at AT TIME ZONE 'UTC') AS utc_hour,
           p.category_id, o.status, COUNT(*) AS order_count, SUM(o.quantity) AS units,
           SUM(o.quantity::bigint * o.unit_price_cents) AS sales_cents
    FROM ax.orders o JOIN ax.products p USING (tenant_id, product_id) GROUP BY 1, 2, 3, 4),
s_hcs AS (
    SELECT tenant_id, utc_hour, category_id, status, order_count, units, sales_cents
    FROM ax.st_hour_category_status)
SELECT 'st_day_product_status',
       (SELECT COUNT(*) FROM (SELECT * FROM o_dps EXCEPT ALL SELECT * FROM s_dps) x),
       (SELECT COUNT(*) FROM (SELECT * FROM s_dps EXCEPT ALL SELECT * FROM o_dps) x)
UNION ALL
SELECT 'st_day_category_status',
       (SELECT COUNT(*) FROM (SELECT * FROM o_dcs EXCEPT ALL SELECT * FROM s_dcs) x),
       (SELECT COUNT(*) FROM (SELECT * FROM s_dcs EXCEPT ALL SELECT * FROM o_dcs) x)
UNION ALL
SELECT 'st_hour_category_status',
       (SELECT COUNT(*) FROM (SELECT * FROM o_hcs EXCEPT ALL SELECT * FROM s_hcs) x),
       (SELECT COUNT(*) FROM (SELECT * FROM s_hcs EXCEPT ALL SELECT * FROM o_hcs) x)) r(stream_table,missing_in_st,extra_in_st);
SELECT json_agg(r) FROM (SELECT pgt_id,pgt_name,status,refresh_mode,effective_refresh_mode,
last_refresh_at,data_timestamp,frontier,tentative_frontier,consecutive_errors,needs_reinit,last_error_at,last_error_code
FROM pgtrickle.pgt_stream_tables WHERE pgt_schema='ax' ORDER BY pgt_name)r;
SELECT json_agg(r) FROM (SELECT s.pgt_name,max(h.end_time) FILTER(WHERE h.status='COMPLETED') latest_completed,
max(h.end_time) FILTER(WHERE h.status='COMPLETED' AND h.action<>'NO_DATA') latest_data_refresh,
count(*) FILTER(WHERE h.status='FAILED') failed,count(*) FILTER(WHERE h.end_time IS NULL) incomplete,
count(*) FILTER(WHERE h.was_full_fallback) fallbacks
FROM pgtrickle.pgt_stream_tables s LEFT JOIN pgtrickle.pgt_refresh_history h USING(pgt_id)
WHERE s.pgt_schema='ax' GROUP BY s.pgt_name ORDER BY s.pgt_name)r;
SELECT json_build_object('table','orders','rows',count(*),'content_md5',md5(string_agg(to_jsonb(t)::text,E'\n' ORDER BY tenant_id,order_id))) FROM (SELECT tenant_id,order_id,product_id,status,quantity,unit_price_cents,created_at,updated_at FROM ax.orders)t;
SELECT json_build_object('table','st_day_product_status','rows',count(*),'content_md5',md5(string_agg(to_jsonb(t)::text,E'\n' ORDER BY tenant_id,utc_day,product_id,status))) FROM (SELECT tenant_id,utc_day,product_id,status,order_count,units,sales_cents FROM ax.st_day_product_status)t;
SELECT json_build_object('table','st_day_category_status','rows',count(*),'content_md5',md5(string_agg(to_jsonb(t)::text,E'\n' ORDER BY tenant_id,utc_day,category_id,status))) FROM (SELECT tenant_id,utc_day,category_id,status,order_count,units,sales_cents FROM ax.st_day_category_status)t;
SELECT json_build_object('table','st_hour_category_status','rows',count(*),'content_md5',md5(string_agg(to_jsonb(t)::text,E'\n' ORDER BY tenant_id,utc_hour,category_id,status))) FROM (SELECT tenant_id,utc_hour,category_id,status,order_count,units,sales_cents FROM ax.st_hour_category_status)t;
SELECT json_agg(t) FROM (SELECT tenant_id,utc_day,product_id,status,order_count,units,sales_cents FROM ax.st_day_product_status WHERE tenant_id=2 AND product_id=116 AND utc_day='2026-10-31' ORDER BY status)t;
ROLLBACK;
