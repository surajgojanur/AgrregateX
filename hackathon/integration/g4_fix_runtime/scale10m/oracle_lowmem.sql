-- Exact stream-table vs source check for large datasets on small hosts (read-only).
-- Same verdict as ax.oracle_mismatches() (symmetric EXCEPT ALL per group), but one table at a time
-- and sort/merge based (hash aggregation and hash joins off), so memory stays bounded and work
-- spills to temp files instead of growing RAM. Written after the 10M run: the all-in-one hashed
-- oracle with work_mem=128MB was OOM-killed inside a 2 GiB container.
-- missing_in_st = source groups with no identical stream-table row; extra_in_st = the reverse.
-- usage: psql -h 127.0.0.1 -p <port> -U postgres -d aggregatex -f oracle_lowmem.sql
\set ON_ERROR_STOP 1
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL enable_hashagg = off;
SET LOCAL enable_hashjoin = off;
SET LOCAL work_mem = '32MB';
SET LOCAL max_parallel_workers_per_gather = 0;

SELECT 'st_day_product_status' AS stream_table,
       count(*) FILTER (WHERE st.tenant_id IS NULL OR (st.order_count, st.units, st.sales_cents) IS DISTINCT FROM (s.c, s.u, s.v)) - count(*) FILTER (WHERE s.tenant_id IS NULL) AS missing_in_st,
       count(*) FILTER (WHERE s.tenant_id IS NULL OR (st.order_count, st.units, st.sales_cents) IS DISTINCT FROM (s.c, s.u, s.v)) - count(*) FILTER (WHERE st.tenant_id IS NULL) AS extra_in_st
FROM (SELECT tenant_id, utc_day, product_id, status, count(*) AS c, sum(quantity) AS u, sum(line_cents) AS v
        FROM ax.orders GROUP BY 1, 2, 3, 4) s
FULL JOIN ax.st_day_product_status st
  ON st.tenant_id = s.tenant_id AND st.utc_day = s.utc_day AND st.product_id = s.product_id AND st.status = s.status;

SELECT 'st_day_category_status' AS stream_table,
       count(*) FILTER (WHERE st.tenant_id IS NULL OR (st.order_count, st.units, st.sales_cents) IS DISTINCT FROM (s.c, s.u, s.v)) - count(*) FILTER (WHERE s.tenant_id IS NULL) AS missing_in_st,
       count(*) FILTER (WHERE s.tenant_id IS NULL OR (st.order_count, st.units, st.sales_cents) IS DISTINCT FROM (s.c, s.u, s.v)) - count(*) FILTER (WHERE st.tenant_id IS NULL) AS extra_in_st
FROM (SELECT o.tenant_id, o.utc_day, p.category_id, o.status, count(*) AS c, sum(o.quantity) AS u, sum(o.line_cents) AS v
        FROM ax.orders o JOIN ax.products p USING (tenant_id, product_id) GROUP BY 1, 2, 3, 4) s
FULL JOIN ax.st_day_category_status st
  ON st.tenant_id = s.tenant_id AND st.utc_day = s.utc_day AND st.category_id = s.category_id AND st.status = s.status;

SELECT 'st_hour_category_status' AS stream_table,
       count(*) FILTER (WHERE st.tenant_id IS NULL OR (st.order_count, st.units, st.sales_cents) IS DISTINCT FROM (s.c, s.u, s.v)) - count(*) FILTER (WHERE s.tenant_id IS NULL) AS missing_in_st,
       count(*) FILTER (WHERE s.tenant_id IS NULL OR (st.order_count, st.units, st.sales_cents) IS DISTINCT FROM (s.c, s.u, s.v)) - count(*) FILTER (WHERE st.tenant_id IS NULL) AS extra_in_st
FROM (SELECT o.tenant_id, o.utc_hour, p.category_id, o.status, count(*) AS c, sum(o.quantity) AS u, sum(o.line_cents) AS v
        FROM ax.orders o JOIN ax.products p USING (tenant_id, product_id) GROUP BY 1, 2, 3, 4) s
FULL JOIN ax.st_hour_category_status st
  ON st.tenant_id = s.tenant_id AND st.utc_hour = s.utc_hour AND st.category_id = s.category_id AND st.status = s.status;
COMMIT;
