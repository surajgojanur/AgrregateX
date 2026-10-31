BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='2s';
SET LOCAL lock_timeout='500ms';
SELECT json_build_object('utc',clock_timestamp() AT TIME ZONE 'UTC','snapshot',txid_current_snapshot()::text);
SELECT json_agg(r) FROM (SELECT order_id,tenant_id,product_id,status,quantity,unit_price_cents,
quantity::bigint*unit_price_cents recomputed_cents,line_cents,created_at,updated_at,utc_day,utc_hour
FROM ax.orders WHERE tenant_id=2 AND product_id=116
AND created_at>='2026-10-31T00:00:00Z' AND created_at<'2026-11-01T00:00:00Z' ORDER BY order_id LIMIT 20)r;
SELECT json_build_object('paid_count',count(*),'paid_units',coalesce(sum(quantity),0),
'paid_sales_cents',coalesce(sum(quantity::bigint*unit_price_cents),0)) FROM ax.orders
WHERE tenant_id=2 AND product_id=116 AND status='paid'
AND created_at>='2026-10-31T00:00:00Z' AND created_at<'2026-11-01T00:00:00Z';
SELECT json_agg(r) FROM (SELECT status,count(*),sum(quantity) units,sum(quantity::bigint*unit_price_cents) cents
FROM ax.orders WHERE tenant_id=2 AND product_id=116
AND created_at>='2026-10-31T00:00:00Z' AND created_at<'2026-11-01T00:00:00Z' GROUP BY status ORDER BY status)r;
SELECT json_agg(r) FROM (SELECT tenant_id,utc_day,product_id,status,order_count,units,sales_cents
FROM ax.st_day_product_status WHERE tenant_id=2 AND product_id=116 AND utc_day='2026-10-31' ORDER BY status)r;
SELECT json_agg(r) FROM (SELECT tenant_id,product_id,category_id FROM ax.products WHERE tenant_id=2 AND product_id=116)r;
SELECT json_agg(r) FROM (SELECT 'source' side,p.category_id,o.status,count(*) order_count,sum(o.quantity) units,
sum(o.quantity::bigint*o.unit_price_cents) sales_cents FROM ax.orders o JOIN ax.products p USING(tenant_id,product_id)
WHERE o.tenant_id=2 AND p.category_id=(SELECT category_id FROM ax.products WHERE tenant_id=2 AND product_id=116)
AND o.created_at>='2026-10-31T00:00:00Z' AND o.created_at<'2026-11-01T00:00:00Z' GROUP BY 2,3
UNION ALL SELECT 'stream',category_id,status,order_count,units,sales_cents FROM ax.st_day_category_status
WHERE tenant_id=2 AND utc_day='2026-10-31' AND category_id=(SELECT category_id FROM ax.products WHERE tenant_id=2 AND product_id=116)
ORDER BY 2,3,1)r;
SELECT json_agg(r) FROM (SELECT 'source' side,date_trunc('hour',o.created_at AT TIME ZONE 'UTC') utc_hour,
p.category_id,o.status,count(*) order_count,sum(o.quantity) units,sum(o.quantity::bigint*o.unit_price_cents) sales_cents
FROM ax.orders o JOIN ax.products p USING(tenant_id,product_id)
WHERE o.tenant_id=2 AND p.category_id=(SELECT category_id FROM ax.products WHERE tenant_id=2 AND product_id=116)
AND o.created_at>='2026-10-31T00:00:00Z' AND o.created_at<'2026-11-01T00:00:00Z' GROUP BY 2,3,4
UNION ALL SELECT 'stream',utc_hour,category_id,status,order_count,units,sales_cents FROM ax.st_hour_category_status
WHERE tenant_id=2 AND utc_hour>='2026-10-31' AND utc_hour<'2026-11-01'
AND category_id=(SELECT category_id FROM ax.products WHERE tenant_id=2 AND product_id=116) ORDER BY 2,3,4,1)r;
SELECT json_agg(r) FROM (SELECT table_name,column_name,data_type FROM information_schema.columns
WHERE table_schema='ax' AND table_name IN ('orders','st_day_product_status','st_day_category_status','st_hour_category_status')
AND column_name IN ('created_at','utc_day','utc_hour','status','order_count','units','sales_cents','line_cents') ORDER BY 1,2)r;
SELECT json_agg(r) FROM (SELECT pgt_name,defining_query,created_at,updated_at FROM pgtrickle.pgt_stream_tables WHERE pgt_schema='ax' ORDER BY pgt_name)r;
SELECT json_build_object('bad_day',count(*) FILTER(WHERE utc_day IS DISTINCT FROM date_trunc('day',created_at AT TIME ZONE 'UTC')),
'bad_hour',count(*) FILTER(WHERE utc_hour IS DISTINCT FROM date_trunc('hour',created_at AT TIME ZONE 'UTC')),
'bad_cents',count(*) FILTER(WHERE line_cents IS DISTINCT FROM quantity::bigint*unit_price_cents)) FROM ax.orders;
ROLLBACK;
