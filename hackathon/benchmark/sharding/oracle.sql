-- Three independent source oracles matching hackathon/sql/10_stream_tables.sql.
-- Run separately on each shard after writes settle. Compare in both directions.
-- Prerequisite: database-local ax.orders and ax.products plus the three stream tables.
WITH expected AS (
 SELECT tenant_id, utc_day, product_id, status, count(*) order_count,
        sum(quantity) units, sum(line_cents) sales_cents
 FROM ax.orders GROUP BY 1,2,3,4
), actual AS (
 SELECT tenant_id, utc_day, product_id, status, order_count, units, sales_cents
 FROM ax.st_day_product_status
)
SELECT 'st_day_product_status' stream_table,
 (SELECT count(*) FROM ((SELECT * FROM expected EXCEPT ALL SELECT * FROM actual)
 UNION ALL (SELECT * FROM actual EXCEPT ALL SELECT * FROM expected)) d) mismatches;

WITH expected AS (
 SELECT o.tenant_id, o.utc_day, p.category_id, o.status, count(*) order_count,
        sum(o.quantity) units, sum(o.line_cents) sales_cents
 FROM ax.orders o JOIN ax.products p USING (tenant_id, product_id)
 GROUP BY 1,2,3,4
), actual AS (
 SELECT tenant_id, utc_day, category_id, status, order_count, units, sales_cents
 FROM ax.st_day_category_status
)
SELECT 'st_day_category_status' stream_table,
 (SELECT count(*) FROM ((SELECT * FROM expected EXCEPT ALL SELECT * FROM actual)
 UNION ALL (SELECT * FROM actual EXCEPT ALL SELECT * FROM expected)) d) mismatches;

WITH expected AS (
 SELECT o.tenant_id, o.utc_hour, p.category_id, o.status, count(*) order_count,
        sum(o.quantity) units, sum(o.line_cents) sales_cents
 FROM ax.orders o JOIN ax.products p USING (tenant_id, product_id)
 GROUP BY 1,2,3,4
), actual AS (
 SELECT tenant_id, utc_hour, category_id, status, order_count, units, sales_cents
 FROM ax.st_hour_category_status
)
SELECT 'st_hour_category_status' stream_table,
 (SELECT count(*) FROM ((SELECT * FROM expected EXCEPT ALL SELECT * FROM actual)
 UNION ALL (SELECT * FROM actual EXCEPT ALL SELECT * FROM expected)) d) mismatches;
