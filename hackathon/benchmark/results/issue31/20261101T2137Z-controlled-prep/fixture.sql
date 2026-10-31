-- PREPARED ONLY: creates/mutates ONLY the separately approved disposable database.
\set ON_ERROR_STOP on
SELECT current_database()='ax_g4_repro' AND current_setting('pg_trickle.enabled',true)='off' AS allowed \gset
\if :allowed
\else
  \echo 'REFUSED: wrong database or scheduler not disabled for this disposable target'
  \quit 3
\endif
CREATE EXTENSION IF NOT EXISTS pg_trickle;
SELECT (SELECT extversion='0.108.3' FROM pg_extension WHERE extname='pg_trickle')
 AND current_setting('server_version') LIKE '18.6%' AS version_ok \gset
\if :version_ok
\else
  \quit 3
\endif
-- Refuse reuse; each experiment needs a new approved fixture, not a silent reset.
SELECT to_regnamespace('ax') IS NULL AS empty_fixture \gset
\if :empty_fixture
\else
  \quit 3
\endif
\i /ax/sql/00_schema.sql
\i /ax/sql/05_bucket_columns.sql
INSERT INTO ax.tenants VALUES (1,'synthetic-one'),(2,'synthetic-isolation-control');
INSERT INTO ax.customers VALUES (1,1,'synthetic'),(2,1,'synthetic');
INSERT INTO ax.products
 SELECT 1,n,CASE WHEN n=2 THEN 2 ELSE 1 END,'synthetic-'||n FROM generate_series(1,100)n;
INSERT INTO ax.products VALUES (2,1,1,'synthetic-control');
-- 80 stable groups for bounded auto DELETE+INSERT selection; cases stay below 100 orders.
INSERT INTO ax.orders(tenant_id,order_id,customer_id,product_id,status,quantity,unit_price_cents,created_at)
 SELECT 1,n,1,n,'paid',1,1000,'2026-09-01T12:00:00Z' FROM generate_series(10,88)n;
INSERT INTO ax.orders(tenant_id,order_id,customer_id,product_id,status,quantity,unit_price_cents,created_at)
 VALUES(2,1,1,1,'paid',1,1000,'2026-09-01T12:00:00Z');
\set mode DIFFERENTIAL
\set sched 1h
\set cdc trigger
\i /ax/sql/10_stream_tables.sql
\i /ax/sql/20_security.sql
-- Baseline only. Observer must confirm actual FULL/reinit vs DIFFERENTIAL history separately.
SELECT pgtrickle.refresh_stream_table('ax.st_day_product_status');
SELECT pgtrickle.refresh_stream_table('ax.st_day_category_status');
SELECT pgtrickle.refresh_stream_table('ax.st_hour_category_status');
ANALYZE ax.st_day_product_status;
ANALYZE ax.st_day_category_status;
ANALYZE ax.st_hour_category_status;
SELECT count(*) <= 100 AS fixture_budget_ok FROM ax.orders \gset
\if :fixture_budget_ok
\else
  \echo 'REFUSED: baseline exceeds 100-order fixture budget'
  \quit 3
\endif
-- Before cases: execute oracle_select.sql, require all 0/0, populated frontiers,
-- no needs_reinit, and no scheduler-driven refreshes. Abort otherwise.
