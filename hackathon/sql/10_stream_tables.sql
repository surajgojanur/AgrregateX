-- AgrregateX ENGINE_CONTRACT v1 — stream tables. REQUIRES 05_bucket_columns.sql
-- (GROUP BY must use plain NOT NULL columns, see that file for the measured reason) (upstream pg_trickle does the maintenance;
-- these definitions, keys and semantics are the AgrregateX contribution).
--
-- psql variables (defaults = recommended primary architecture):
--   :mode   'DIFFERENTIAL' | 'AUTO' | 'IMMEDIATE' | 'FULL'
--   :sched  '1s' | '5s' | '10s'  (ignored/NULL for IMMEDIATE)
--   :cdc    'trigger' | 'wal' | 'auto'
-- Example: psql -v mode=DIFFERENTIAL -v sched=1s -v cdc=trigger -f 10_stream_tables.sql
\if :{?mode}
\else
  \set mode DIFFERENTIAL
\endif
\if :{?sched}
\else
  \set sched 1s
\endif
\if :{?cdc}
\else
  \set cdc trigger
\endif

-- Per-statement IMMEDIATE has no schedule.
SELECT CASE WHEN :'mode' = 'IMMEDIATE' THEN '' ELSE :'sched' END AS eff_sched \gset

-- 1) Top-N products + daily summaries: one row per (tenant, UTC day, product, status).
--    All product totals are kept (never a pre-cut Top-N) so any range re-ranks exactly.
SELECT pgtrickle.create_stream_table(
    name         => 'ax.st_day_product_status',
    query        => $q$
        SELECT o.tenant_id, o.utc_day, o.product_id, o.status,
               COUNT(*)            AS order_count,
               SUM(o.quantity)     AS units,
               SUM(o.line_cents)   AS sales_cents
        FROM ax.orders o
        GROUP BY o.tenant_id, o.utc_day, o.product_id, o.status
    $q$,
    schedule     => NULLIF(:'eff_sched', ''),
    refresh_mode => :'mode',
    cdc_mode     => :'cdc'
);

-- 2) Category/status breakdown over long ranges (joins products for category).
SELECT pgtrickle.create_stream_table(
    name         => 'ax.st_day_category_status',
    query        => $q$
        SELECT o.tenant_id, o.utc_day, p.category_id, o.status,
               COUNT(*)            AS order_count,
               SUM(o.quantity)     AS units,
               SUM(o.line_cents)   AS sales_cents
        FROM ax.orders o
        JOIN ax.products p ON p.tenant_id = o.tenant_id AND p.product_id = o.product_id
        GROUP BY o.tenant_id, o.utc_day, p.category_id, o.status
    $q$,
    schedule     => NULLIF(:'eff_sched', ''),
    refresh_mode => :'mode',
    cdc_mode     => :'cdc'
);

-- 3) Hourly trends / hourly category breakdown.
SELECT pgtrickle.create_stream_table(
    name         => 'ax.st_hour_category_status',
    query        => $q$
        SELECT o.tenant_id, o.utc_hour, p.category_id, o.status,
               COUNT(*)            AS order_count,
               SUM(o.quantity)     AS units,
               SUM(o.line_cents)   AS sales_cents
        FROM ax.orders o
        JOIN ax.products p ON p.tenant_id = o.tenant_id AND p.product_id = o.product_id
        GROUP BY o.tenant_id, o.utc_hour, p.category_id, o.status
    $q$,
    schedule     => NULLIF(:'eff_sched', ''),
    refresh_mode => :'mode',
    cdc_mode     => :'cdc'
);

-- Read-path indexes: NONE added. pg_trickle auto_index already creates
-- (tenant_id, utc_<grain>, <dim>, status) on every stream table; its prefix serves
-- tenant+range scans. Extra indexes only add refresh (MERGE) cost.
