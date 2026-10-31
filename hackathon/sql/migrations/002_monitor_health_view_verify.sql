-- Issue #34: run AFTER approval and applying 002_monitor_health_view.sql.
-- Execute as the actual ax_monitor login (NOT postgres) against aggregatex:25560.
-- READ ONLY: prints metadata health and verifies no raw tenant-row permissions.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '2s';
DO $check$
BEGIN
    IF current_database() <> 'aggregatex' OR current_user <> 'ax_monitor' THEN
        RAISE EXCEPTION 'Verification must connect directly as ax_monitor to aggregatex';
    END IF;
    IF NOT has_table_privilege(current_user,'pgtrickle.stream_tables_info','SELECT')
       OR has_table_privilege(current_user,'ax.orders','SELECT')
       OR has_table_privilege(current_user,'ax.products','SELECT') THEN
        RAISE EXCEPTION 'Monitor view privilege missing or raw-order/product privilege leaked';
    END IF;
END
$check$;

-- This view is an extension CATALOG view, not tenant fact data.
SELECT pgt_schema, pgt_name, stale
  FROM pgtrickle.stream_tables_info
 WHERE pgt_schema = 'ax' ORDER BY pgt_name LIMIT 10;

-- If this errors, migration is NOT independently verified: investigate, do not
-- change the UI to declare a healthy state. WARN/ERROR rows remain meaningful.
SELECT check_name, severity, detail
  FROM pgtrickle.health_check()
 ORDER BY check_name;
ROLLBACK;
