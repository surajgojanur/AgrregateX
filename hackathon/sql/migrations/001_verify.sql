-- Read-only correctness/permission validation; run as the trusted owner after migration.
BEGIN READ ONLY;
SET LOCAL statement_timeout='10s';
DO $$ BEGIN
 IF EXISTS ((SELECT * FROM ax.tenant_order_counts() EXCEPT SELECT tenant_id,count(*),count(*) FILTER(WHERE order_id<100000000) FROM ax.orders GROUP BY 1)
 UNION ALL (SELECT tenant_id,count(*),count(*) FILTER(WHERE order_id<100000000) FROM ax.orders GROUP BY 1 EXCEPT SELECT * FROM ax.tenant_order_counts())) THEN
 RAISE EXCEPTION 'Aggregate counts differ'; END IF;
 IF (SELECT count(*)<>count(DISTINCT tenant_id) FROM ax.tenant_order_counts()) THEN RAISE EXCEPTION 'Duplicate tenants'; END IF;
 IF NOT has_function_privilege('ax_monitor','ax.tenant_order_counts()','EXECUTE') OR has_function_privilege('ax_api','ax.tenant_order_counts()','EXECUTE') OR has_function_privilege('ax_writer','ax.tenant_order_counts()','EXECUTE') OR has_table_privilege('ax_monitor','ax.orders','SELECT') THEN RAISE EXCEPTION 'Unexpected privileges'; END IF;
END $$;
ROLLBACK;
