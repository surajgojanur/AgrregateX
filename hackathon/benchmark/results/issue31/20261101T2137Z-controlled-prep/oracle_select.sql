\set ON_ERROR_STOP on
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='2s';
SELECT current_database()='ax_g4_repro' AS allowed \gset
\if :allowed
\else
  ROLLBACK;
  \quit 3
\endif
SELECT clock_timestamp() AT TIME ZONE 'UTC' AS observed_utc, txid_current_snapshot()::text AS snapshot;
SELECT * FROM (WITH
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
ROLLBACK;
