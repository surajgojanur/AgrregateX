-- AgrregateX app roles (run AFTER 20_security.sql, BEFORE reinitialize; see handoff F7).
--   ax_api      read-only tenant data (created in 20_security.sql), RLS-bound
--   ax_writer   tenant-scoped writes for the live demo writer / demo endpoint, RLS-bound
--   ax_monitor  engine internals only (pg_trickle catalog, no tenant rows)
-- Passwords are set by the deployment (hackathon/app/db/init.sh from env), never committed.

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ax_writer') THEN
        CREATE ROLE ax_writer LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ax_monitor') THEN
        CREATE ROLE ax_monitor LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
    END IF;
END $$;

-- New order ids for live writes (seed data uses 1..N).
CREATE SEQUENCE IF NOT EXISTS ax.order_id_seq START 100000000;

GRANT USAGE ON SCHEMA ax TO ax_writer;
GRANT SELECT, INSERT, UPDATE ON ax.orders TO ax_writer;
GRANT USAGE ON SEQUENCE ax.order_id_seq TO ax_writer;
DROP POLICY IF EXISTS tenant_write ON ax.orders;
CREATE POLICY tenant_write ON ax.orders FOR ALL TO ax_writer
    USING (tenant_id = ax.current_tenant()) WITH CHECK (tenant_id = ax.current_tenant());

-- Monitoring: pg_trickle catalog + tenant directory, never tenant fact rows.
GRANT pg_monitor TO ax_monitor;
GRANT USAGE ON SCHEMA pgtrickle, ax TO ax_monitor;
GRANT SELECT ON pgtrickle.pgt_stream_tables, pgtrickle.pgt_refresh_history TO ax_monitor;
-- pgtrickle.health_check() reads this catalog-only view. This does NOT grant
-- raw tenant fact rows; the view is built from pgtrickle.pgt_stream_tables.
GRANT SELECT ON pgtrickle.stream_tables_info TO ax_monitor;
GRANT SELECT ON ax.tenants TO ax_monitor;

-- Aggregate-only order counts for the operator /api/shards view: ax_monitor never reads order
-- rows, only per-tenant totals. SECURITY DEFINER with a pinned search_path.
CREATE OR REPLACE FUNCTION ax.tenant_order_counts()
RETURNS TABLE (tenant_id integer, orders bigint, seed_orders bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, ax AS $f$
    SELECT o.tenant_id, count(*), count(*) FILTER (WHERE o.order_id < 100000000)
      FROM ax.orders o GROUP BY o.tenant_id
$f$;
REVOKE ALL ON FUNCTION ax.tenant_order_counts() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION ax.tenant_order_counts() TO ax_monitor;
