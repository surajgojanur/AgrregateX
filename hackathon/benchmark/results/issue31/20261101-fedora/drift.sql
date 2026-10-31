BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='2s';
WITH expected AS (
 SELECT tenant_id,date_trunc('day',created_at AT TIME ZONE 'UTC') utc_day,product_id,status,
 count(*) order_count,sum(quantity) units,sum(quantity::bigint*unit_price_cents) sales_cents
 FROM ax.orders GROUP BY 1,2,3,4), actual AS (
 SELECT tenant_id,utc_day,product_id,status,order_count,units,sales_cents FROM ax.st_day_product_status)
SELECT 'extra' direction,to_jsonb(d) row FROM (SELECT * FROM actual EXCEPT ALL SELECT * FROM expected)d
UNION ALL SELECT 'missing',to_jsonb(d) FROM (SELECT * FROM expected EXCEPT ALL SELECT * FROM actual)d;
SELECT action,status,count(*) FROM pgtrickle.pgt_refresh_history GROUP BY 1,2 ORDER BY 1,2;
ROLLBACK;
