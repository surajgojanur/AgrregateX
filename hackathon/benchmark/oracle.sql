-- Read-only symmetric multiset comparison. Run after writers stop and visibility converges.
-- Does not trust freshness timestamps. Any mismatch is failure.
WITH expected AS (
 SELECT tenant_id, date_trunc('day', created_at AT TIME ZONE 'UTC') utc_day,
 product_id, status, count(*) order_count, sum(quantity) units,
 sum(quantity::bigint * unit_price_cents) sales_cents
 FROM ax.orders GROUP BY 1,2,3,4
), actual AS (
 SELECT tenant_id, utc_day, product_id, status, order_count, units, sales_cents
 FROM ax.st_day_product_status
)
SELECT count(*) AS mismatches FROM (
 (SELECT * FROM expected EXCEPT ALL SELECT * FROM actual)
 UNION ALL (SELECT * FROM actual EXCEPT ALL SELECT * FROM expected)
) differences;
