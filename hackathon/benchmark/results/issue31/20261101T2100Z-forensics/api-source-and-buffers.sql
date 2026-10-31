BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='2s'; SET LOCAL lock_timeout='500ms';
SELECT json_build_object('utc',clock_timestamp() AT TIME ZONE 'UTC','snapshot',txid_current_snapshot()::text);
SELECT json_agg(r) FROM (SELECT status,count(*) orders,sum(quantity) units,sum(quantity::bigint*unit_price_cents) gross_cents
FROM ax.orders WHERE tenant_id=2 AND created_at>='2026-10-31T00:00:00Z' AND created_at<'2026-11-01T00:00:00Z'
GROUP BY status ORDER BY status)r;
SELECT json_agg(r) FROM (SELECT product_id,count(*) orders,sum(quantity) units,sum(quantity::bigint*unit_price_cents) sales_cents
FROM ax.orders WHERE tenant_id=2 AND created_at>='2026-10-31T00:00:00Z' AND created_at<'2026-11-01T00:00:00Z'
AND status NOT IN ('cancelled','refunded') GROUP BY product_id ORDER BY sales_cents DESC,product_id LIMIT 10)r;
SELECT json_agg(r) FROM (SELECT change_id,lsn,action,source_xid,source_commit_at,tenant_id,order_id,product_id,status,quantity,line_cents,created_at,updated_at
FROM pgtrickle_changes.changes_daaaeeb1fdc57e97 ORDER BY change_id LIMIT 10)r;
SELECT json_agg(r) FROM (SELECT change_id,lsn,action,tenant_id,product_id,category_id FROM pgtrickle_changes.changes_1d8a10d0e8bcdd15 ORDER BY change_id LIMIT 10)r;
SELECT json_agg(r) FROM (SELECT tenant_id,utc_day,product_id,status,count(*) copies FROM ax.st_day_product_status
WHERE tenant_id=2 AND product_id=116 AND utc_day='2026-10-31' GROUP BY 1,2,3,4 ORDER BY status)r;
ROLLBACK;
