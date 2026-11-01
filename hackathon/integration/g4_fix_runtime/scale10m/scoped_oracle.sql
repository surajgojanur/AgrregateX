-- Scoped exact check (same method as oracle_lowmem.sql: sort/merge, bounded memory), limited to tenants 1-2 and
-- the window every case writes into, [2026-09-01, 2026-09-09). Fast enough to run after EACH case at 10M.
-- The full 10M oracle runs at the start and the end.
CREATE OR REPLACE FUNCTION g4r.scoped() RETURNS TABLE (stream_table text, missing bigint, extra bigint)
LANGUAGE sql STABLE SET enable_hashagg = off SET enable_hashjoin = off SET work_mem = '32MB' AS $f$
WITH lo AS (SELECT timestamp '2026-09-01' AS a, timestamp '2026-09-09' AS b)
SELECT 'st_day_product_status',
  count(*) FILTER (WHERE st.tenant_id IS NULL OR (st.order_count, st.units, st.sales_cents) IS DISTINCT FROM (s.c, s.u, s.v)) - count(*) FILTER (WHERE s.tenant_id IS NULL),
  count(*) FILTER (WHERE s.tenant_id IS NULL OR (st.order_count, st.units, st.sales_cents) IS DISTINCT FROM (s.c, s.u, s.v)) - count(*) FILTER (WHERE st.tenant_id IS NULL)
FROM (SELECT tenant_id, utc_day, product_id, status, count(*) c, sum(quantity) u, sum(quantity::bigint * unit_price_cents) v
        FROM ax.orders, lo WHERE tenant_id IN (1, 2) AND utc_day >= lo.a AND utc_day < lo.b GROUP BY 1, 2, 3, 4) s
FULL JOIN (SELECT d.* FROM ax.st_day_product_status d, lo WHERE tenant_id IN (1, 2) AND utc_day >= lo.a AND utc_day < lo.b) st
  ON st.tenant_id = s.tenant_id AND st.utc_day = s.utc_day AND st.product_id = s.product_id AND st.status = s.status
UNION ALL
SELECT 'st_day_category_status',
  count(*) FILTER (WHERE st.tenant_id IS NULL OR (st.order_count, st.units, st.sales_cents) IS DISTINCT FROM (s.c, s.u, s.v)) - count(*) FILTER (WHERE s.tenant_id IS NULL),
  count(*) FILTER (WHERE s.tenant_id IS NULL OR (st.order_count, st.units, st.sales_cents) IS DISTINCT FROM (s.c, s.u, s.v)) - count(*) FILTER (WHERE st.tenant_id IS NULL)
FROM (SELECT o.tenant_id, o.utc_day, p.category_id, o.status, count(*) c, sum(o.quantity) u, sum(o.quantity::bigint * o.unit_price_cents) v
        FROM ax.orders o JOIN ax.products p USING (tenant_id, product_id), lo
       WHERE o.tenant_id IN (1, 2) AND o.utc_day >= lo.a AND o.utc_day < lo.b GROUP BY 1, 2, 3, 4) s
FULL JOIN (SELECT d.* FROM ax.st_day_category_status d, lo WHERE tenant_id IN (1, 2) AND utc_day >= lo.a AND utc_day < lo.b) st
  ON st.tenant_id = s.tenant_id AND st.utc_day = s.utc_day AND st.category_id = s.category_id AND st.status = s.status
UNION ALL
SELECT 'st_hour_category_status',
  count(*) FILTER (WHERE st.tenant_id IS NULL OR (st.order_count, st.units, st.sales_cents) IS DISTINCT FROM (s.c, s.u, s.v)) - count(*) FILTER (WHERE s.tenant_id IS NULL),
  count(*) FILTER (WHERE s.tenant_id IS NULL OR (st.order_count, st.units, st.sales_cents) IS DISTINCT FROM (s.c, s.u, s.v)) - count(*) FILTER (WHERE st.tenant_id IS NULL)
FROM (SELECT o.tenant_id, o.utc_hour, p.category_id, o.status, count(*) c, sum(o.quantity) u, sum(o.quantity::bigint * o.unit_price_cents) v
        FROM ax.orders o JOIN ax.products p USING (tenant_id, product_id), lo
       WHERE o.tenant_id IN (1, 2) AND o.utc_hour >= lo.a AND o.utc_hour < lo.b GROUP BY 1, 2, 3, 4) s
FULL JOIN (SELECT d.* FROM ax.st_hour_category_status d, lo WHERE tenant_id IN (1, 2) AND utc_hour >= lo.a AND utc_hour < lo.b) st
  ON st.tenant_id = s.tenant_id AND st.utc_hour = s.utc_hour AND st.category_id = s.category_id AND st.status = s.status
$f$;
