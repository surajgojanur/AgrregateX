-- AgrregateX ENGINE_CONTRACT v1 — direct-SQL oracle.
-- ax.oracle_mismatches() recomputes every stream table from raw sources and returns
-- the row-count of the symmetric difference (EXCEPT ALL both ways) per stream table.
-- Correct = every row (0, 0). Run only after writers are quiesced and the stream tables
-- have refreshed past the last commit (see integration/wait_fresh.sql), or inside one
-- REPEATABLE READ snapshot together with IMMEDIATE mode.

CREATE OR REPLACE FUNCTION ax.oracle_mismatches()
RETURNS TABLE (stream_table text, missing_in_st bigint, extra_in_st bigint)
LANGUAGE sql STABLE AS $f$
WITH
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
       (SELECT COUNT(*) FROM (SELECT * FROM s_hcs EXCEPT ALL SELECT * FROM o_hcs) x)
$f$;

-- Effective-mode audit: what each refresh ACTUALLY did since :since (timestamptz).
-- A configured DIFFERENTIAL table whose rows show FULL / was_full_fallback is a FAIL.
CREATE OR REPLACE FUNCTION ax.refresh_audit(since timestamptz)
RETURNS TABLE (stream_table text, action text, fallback bool, reason text,
               refreshes bigint, p50_ms numeric, max_ms numeric, failed bigint)
LANGUAGE sql STABLE AS $f$
SELECT st.pgt_name::text, h.action, h.was_full_fallback, h.refresh_reason,
       COUNT(*),
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM h.end_time - h.start_time) * 1000))::numeric, 1),
       round(max(extract(epoch FROM h.end_time - h.start_time) * 1000)::numeric, 1),
       COUNT(*) FILTER (WHERE h.status = 'FAILED')
FROM pgtrickle.pgt_refresh_history h
JOIN pgtrickle.pgt_stream_tables st USING (pgt_id)
WHERE h.start_time >= since AND st.pgt_schema = 'ax'
GROUP BY 1, 2, 3, 4
ORDER BY 1, 2
$f$;
