-- Verify a synthetic scale dataset after load. Read-only.
-- usage: psql -h 127.0.0.1 -p <db port> -U postgres -d aggregatex -f verify_dataset.sql
\set ON_ERROR_STOP 1
\pset footer off
\echo '--- generator parameters and load time'
SELECT p.orders AS generated_ids, p.tenants, p.seed, p.zipf_s, p.shard_tenants,
       count(g.*) AS chunks, sum(g.rows_inserted) AS rows_inserted,
       round(extract(epoch FROM max(g.committed_at) - p.started_at)::numeric, 1) AS load_s
FROM ax_gen.params p LEFT JOIN ax_gen.progress g ON true
GROUP BY p.orders, p.tenants, p.seed, p.zipf_s, p.shard_tenants, p.started_at;

\echo '--- size on disk'
SELECT pg_size_pretty(pg_database_size(current_database())) AS database,
       pg_size_pretty(pg_table_size('ax.orders'))   AS orders_heap,
       pg_size_pretty(pg_indexes_size('ax.orders')) AS orders_indexes;

\echo '--- tenant skew (largest, median, smallest)'
WITH c AS (SELECT tenant_id, count(*) AS n FROM ax.orders WHERE order_id < 100000000 GROUP BY tenant_id),
     r AS (SELECT tenant_id, n, round(100.0 * n / sum(n) OVER (), 2) AS pct,
                  row_number() OVER (ORDER BY n DESC) AS rk, count(*) OVER () AS k FROM c)
SELECT rk, tenant_id, n AS orders, pct AS pct_of_total FROM r
WHERE rk IN (1, 2, 3, (k + 1) / 2, k) ORDER BY rk;

\echo '--- time window and status mix'
SELECT min(created_at), max(created_at), count(DISTINCT utc_day) AS days FROM ax.orders;
SELECT status, count(*), round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct
FROM ax.orders GROUP BY status ORDER BY 2 DESC;

\echo '--- stream tables: rows, status, refresh mode'
SELECT pgt_name, status, refresh_mode, effective_refresh_mode,
       pg_size_pretty(pg_total_relation_size(pgt_relid)) AS size
FROM pgtrickle.pgt_stream_tables ORDER BY pgt_name;
SELECT 'st_day_product_status' AS st, count(*) AS rows FROM ax.st_day_product_status
UNION ALL SELECT 'st_day_category_status', count(*) FROM ax.st_day_category_status
UNION ALL SELECT 'st_hour_category_status', count(*) FROM ax.st_hour_category_status;

\echo '--- exact reconciliation: stream tables vs source (must be 0 mismatched groups)'
SELECT 'st_day_product_status' AS st, count(*) AS mismatched_groups FROM (
    (SELECT tenant_id, utc_day, product_id, status, count(*) AS c, sum(quantity) AS u, sum(line_cents) AS s
       FROM ax.orders GROUP BY 1, 2, 3, 4
     EXCEPT ALL
     SELECT tenant_id, utc_day, product_id, status, order_count, units, sales_cents FROM ax.st_day_product_status)
    UNION ALL
    (SELECT tenant_id, utc_day, product_id, status, order_count, units, sales_cents FROM ax.st_day_product_status
     EXCEPT ALL
     SELECT tenant_id, utc_day, product_id, status, count(*), sum(quantity), sum(line_cents)
       FROM ax.orders GROUP BY 1, 2, 3, 4)) d
UNION ALL
SELECT 'st_day_category_status', count(*) FROM (
    (SELECT o.tenant_id, o.utc_day, p.category_id, o.status, count(*), sum(o.quantity), sum(o.line_cents)
       FROM ax.orders o JOIN ax.products p USING (tenant_id, product_id) GROUP BY 1, 2, 3, 4
     EXCEPT ALL
     SELECT tenant_id, utc_day, category_id, status, order_count, units, sales_cents FROM ax.st_day_category_status)
    UNION ALL
    (SELECT tenant_id, utc_day, category_id, status, order_count, units, sales_cents FROM ax.st_day_category_status
     EXCEPT ALL
     SELECT o.tenant_id, o.utc_day, p.category_id, o.status, count(*), sum(o.quantity), sum(o.line_cents)
       FROM ax.orders o JOIN ax.products p USING (tenant_id, product_id) GROUP BY 1, 2, 3, 4)) d
UNION ALL
SELECT 'st_hour_category_status', count(*) FROM (
    (SELECT o.tenant_id, o.utc_hour, p.category_id, o.status, count(*), sum(o.quantity), sum(o.line_cents)
       FROM ax.orders o JOIN ax.products p USING (tenant_id, product_id) GROUP BY 1, 2, 3, 4
     EXCEPT ALL
     SELECT tenant_id, utc_hour, category_id, status, order_count, units, sales_cents FROM ax.st_hour_category_status)
    UNION ALL
    (SELECT tenant_id, utc_hour, category_id, status, order_count, units, sales_cents FROM ax.st_hour_category_status
     EXCEPT ALL
     SELECT o.tenant_id, o.utc_hour, p.category_id, o.status, count(*), sum(o.quantity), sum(o.line_cents)
       FROM ax.orders o JOIN ax.products p USING (tenant_id, product_id) GROUP BY 1, 2, 3, 4)) d;

\echo '--- refresh actions since boot (expect DIFFERENTIAL / NO_DATA, no FAILED)'
SELECT action, status, count(*) FROM pgtrickle.pgt_refresh_history GROUP BY 1, 2 ORDER BY 3 DESC;
