-- #54 / #67 runtime regression fixture. Disposable native instance only (refuses anything else).
\set ON_ERROR_STOP on
SELECT current_database() = 'ax_g4_regress' AND current_setting('pg_trickle.enabled', true) = 'off'
       AND to_regnamespace('ax') IS NULL AS allowed \gset
\if :allowed
\else
  \echo 'REFUSED: not the empty ax_g4_regress database with the scheduler disabled'
  \quit 3
\endif
CREATE EXTENSION IF NOT EXISTS pg_trickle;
\i :sqldir/00_schema.sql
\i :sqldir/05_bucket_columns.sql
INSERT INTO ax.tenants VALUES (1, 'regress-one'), (2, 'regress-two');
INSERT INTO ax.customers SELECT t, c, 'c' || c FROM generate_series(1, 2) t, generate_series(1, 5) c;
INSERT INTO ax.products SELECT 1, n, (n % 4) + 1, 'p' || n FROM generate_series(1, 40) n;
INSERT INTO ax.products SELECT 2, n, (n % 2) + 1, 'p' || n FROM generate_series(1, 10) n;
-- 2,000 + 200 orders spread over 10 days, 5 statuses: change ratios per case stay tiny (DIFFERENTIAL path).
INSERT INTO ax.orders (tenant_id, order_id, customer_id, product_id, status, quantity, unit_price_cents, created_at)
SELECT 1, n, (n % 5) + 1, (n % 40) + 1,
       (ARRAY['pending','paid','shipped','cancelled','refunded'])[(n % 5) + 1],
       (n % 3) + 1, 1000 + (n % 7) * 100,
       timestamptz '2026-09-01 00:00:00+00' + (n % 10) * interval '1 day' + (n % 24) * interval '1 hour'
  FROM generate_series(1, 2000) n;
INSERT INTO ax.orders (tenant_id, order_id, customer_id, product_id, status, quantity, unit_price_cents, created_at)
SELECT 2, 5000 + n, (n % 5) + 1, (n % 10) + 1, 'paid', 1, 500,
       timestamptz '2026-09-01 00:00:00+00' + (n % 10) * interval '1 day'
  FROM generate_series(1, 200) n;
\set mode DIFFERENTIAL
\set sched 1h
\set cdc trigger
\i :sqldir/10_stream_tables.sql
\i :sqldir/20_security.sql
\i :sqldir/25_app_roles.sql
SELECT pgtrickle.reinitialize_stream_table(n)
  FROM unnest(ARRAY['ax.st_day_product_status','ax.st_day_category_status','ax.st_hour_category_status']) n;
\i :sqldir/30_oracle.sql
-- Populate once (FULL/REINIT expected here); cases only count refreshes after the mark below.
SELECT pgtrickle.refresh_stream_table(n)
  FROM unnest(ARRAY['ax.st_day_product_status','ax.st_day_category_status','ax.st_hour_category_status']) n;
ANALYZE;

CREATE SCHEMA g4r;
CREATE TABLE g4r.results (case_id text, product text, category text, hour text, actions text,
                          non_differential int, ok boolean, at timestamptz DEFAULT clock_timestamp());
CREATE TABLE g4r.mark (refresh_id bigint);
INSERT INTO g4r.mark SELECT coalesce(max(refresh_id), 0) FROM pgtrickle.pgt_refresh_history;
