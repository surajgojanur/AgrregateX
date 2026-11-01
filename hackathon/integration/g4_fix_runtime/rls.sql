-- A15: forced RLS as ax_api. Each tenant sees exactly its own stream rows; no setting = zero rows.
\set ON_ERROR_STOP on
CREATE TEMP TABLE truth AS
SELECT t, (SELECT count(*) FROM ax.st_day_product_status WHERE tenant_id = t) dps,
          (SELECT count(*) FROM ax.st_day_category_status WHERE tenant_id = t) dcs,
          (SELECT count(*) FROM ax.st_hour_category_status WHERE tenant_id = t) hcs,
          (SELECT count(*) FROM ax.orders WHERE tenant_id = t) o
  FROM unnest(ARRAY[1, 2]) t;
GRANT SELECT ON truth TO ax_api;
SET ROLE ax_api;
BEGIN; SELECT set_config('ax.tenant_id', '1', true);
SELECT 'tenant1' AS who, (SELECT count(*) FROM ax.st_day_product_status) = (SELECT dps FROM truth WHERE t = 1)
       AND (SELECT count(*) FROM ax.st_day_category_status) = (SELECT dcs FROM truth WHERE t = 1)
       AND (SELECT count(*) FROM ax.st_hour_category_status) = (SELECT hcs FROM truth WHERE t = 1)
       AND (SELECT count(*) FROM ax.orders) = (SELECT o FROM truth WHERE t = 1)
       AND NOT EXISTS (SELECT 1 FROM ax.st_day_product_status WHERE tenant_id <> 1) AS ok; COMMIT;
BEGIN; SELECT set_config('ax.tenant_id', '2', true);
SELECT 'tenant2' AS who, (SELECT count(*) FROM ax.st_day_product_status) = (SELECT dps FROM truth WHERE t = 2)
       AND (SELECT count(*) FROM ax.orders) = (SELECT o FROM truth WHERE t = 2)
       AND NOT EXISTS (SELECT 1 FROM ax.st_day_category_status WHERE tenant_id <> 2) AS ok; COMMIT;
BEGIN;
SELECT 'no_tenant_setting' AS who, (SELECT count(*) FROM ax.st_day_product_status) + (SELECT count(*) FROM ax.orders) = 0 AS ok;
COMMIT;
BEGIN; SELECT set_config('ax.tenant_id', '1', true); COMMIT;
SELECT 'setting_is_transaction_local' AS who, (SELECT count(*) FROM ax.orders) = 0 AS ok;
RESET ROLE;
