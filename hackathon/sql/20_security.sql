-- AgrregateX ENGINE_CONTRACT v1 — tenant isolation (shared-DB topology).
-- Stream tables are ordinary tables: pg_trickle does NOT apply source RLS to readers.
-- We therefore FORCE RLS on every stream table and on the raw edge-scan source.
--
-- API contract: the API connects as ax_api (no BYPASSRLS, not owner) and, inside each
-- request transaction, runs:  SELECT set_config('ax.tenant_id', '<verified id>', true);
-- Missing/empty setting => policy compares to NULL => zero rows (fail closed).
--
-- Stream-table owner stays the superuser/extension owner: pg_trickle only admits a
-- RLS-enabled SOURCE (ax.orders) to DIFFERENTIAL for a superuser/BYPASSRLS owner.

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ax_api') THEN
        -- Password is set out-of-band by deployment; never commit one.
        CREATE ROLE ax_api LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
    END IF;
END $$;

GRANT USAGE ON SCHEMA ax TO ax_api;
GRANT SELECT ON ax.st_day_product_status, ax.st_day_category_status,
                ax.st_hour_category_status, ax.orders, ax.products TO ax_api;
-- Freshness/monitoring reads (public_read API class in pg_trickle).
GRANT USAGE ON SCHEMA pgtrickle TO ax_api;
-- Never: pgtrickle_changes.* (internal change buffers).

CREATE OR REPLACE FUNCTION ax.current_tenant() RETURNS integer
LANGUAGE sql STABLE AS $f$ SELECT NULLIF(current_setting('ax.tenant_id', true), '')::integer $f$;

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['st_day_product_status','st_day_category_status',
                             'st_hour_category_status','orders','products'] LOOP
        EXECUTE format('ALTER TABLE ax.%I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE ax.%I FORCE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS tenant_read ON ax.%I', t);
        EXECUTE format('CREATE POLICY tenant_read ON ax.%I FOR SELECT TO ax_api '
                       'USING (tenant_id = ax.current_tenant())', t);
    END LOOP;
END $$;
