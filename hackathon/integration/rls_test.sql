-- Negative/positive isolation tests, run as superuser; switches to ax_api via SET ROLE.
\set ON_ERROR_STOP 1
SET ROLE ax_api;
\echo T1 no tenant set -> expect 0 rows everywhere (fail closed)
SELECT 'T1', (SELECT count(*) FROM ax.st_day_product_status) dps, (SELECT count(*) FROM ax.st_hour_category_status) hcs, (SELECT count(*) FROM ax.orders) orders;
BEGIN; SELECT set_config('ax.tenant_id', '2', true);
\echo T2 tenant 2 -> only tenant 2 rows; explicit filter on tenant 1 -> 0
SELECT 'T2', (SELECT count(DISTINCT tenant_id) FROM ax.st_day_product_status) distinct_tenants,
             (SELECT min(tenant_id) FROM ax.st_day_category_status) min_t,
             (SELECT count(*) FROM ax.st_day_product_status WHERE tenant_id = 1) t1_rows_visible,
             (SELECT count(*) FROM ax.orders WHERE tenant_id = 1) t1_orders_visible;
COMMIT;
\echo T3 setting is transaction-local -> after COMMIT back to 0 rows
SELECT 'T3', (SELECT count(*) FROM ax.st_day_product_status) dps;
\echo T4 garbage tenant value -> error (not data)
BEGIN; SELECT set_config('ax.tenant_id', '1 OR 1=1', true);
\set ON_ERROR_STOP 0
SELECT 'T4', count(*) FROM ax.st_day_product_status;
\set ON_ERROR_STOP 1
ROLLBACK;
\echo T5 api role cannot read change buffers or write stream tables
\set ON_ERROR_STOP 0
SELECT 'T5a', count(*) FROM pgtrickle_changes.changes_daaaeeb1fdc57e97;
DELETE FROM ax.st_day_product_status;
\set ON_ERROR_STOP 1
RESET ROLE;
