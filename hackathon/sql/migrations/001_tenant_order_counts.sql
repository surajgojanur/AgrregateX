-- Existing Fedora demo repair: helper only; no role, policy, sequence or source-data changes.
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '10s';
DO $guard$
DECLARE f pg_proc; own oid;
BEGIN
  IF current_database() <> 'aggregatex' OR current_user <> 'postgres' THEN
    RAISE EXCEPTION 'Expected aggregatex database and trusted postgres migration owner';
  END IF;
  SELECT relowner INTO own FROM pg_class WHERE oid = 'ax.orders'::regclass;
  IF own <> (SELECT oid FROM pg_roles WHERE rolname = current_user)
     OR NOT (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) THEN
    RAISE EXCEPTION 'Unexpected source owner or untrusted migration role';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ax_monitor' AND NOT rolsuper AND NOT rolbypassrls)
     OR has_table_privilege('ax_monitor','ax.orders','SELECT')
     OR NOT has_schema_privilege('ax_monitor','ax','USAGE') THEN
    RAISE EXCEPTION 'Unexpected monitor privileges';
  END IF;
  IF (SELECT count(*) FROM information_schema.columns WHERE table_schema='ax' AND table_name='orders'
      AND ((column_name='tenant_id' AND data_type='integer') OR (column_name='order_id' AND data_type='bigint'))) <> 2 THEN
    RAISE EXCEPTION 'Incompatible source columns';
  END IF;
  IF to_regprocedure('ax.tenant_order_counts()') IS NOT NULL THEN
    SELECT * INTO f FROM pg_proc WHERE oid='ax.tenant_order_counts()'::regprocedure;
    IF btrim(regexp_replace(f.prosrc, '\s+', ' ', 'g')) <> 'SELECT o.tenant_id, count(*), count(*) FILTER (WHERE o.order_id < 100000000) FROM ax.orders o GROUP BY o.tenant_id'
       OR NOT f.prosecdef OR f.provolatile <> 's' OR f.proowner <> own
       OR f.proconfig IS DISTINCT FROM ARRAY['search_path=pg_catalog, ax']
       OR pg_get_function_result(f.oid) <> 'TABLE(tenant_id integer, orders bigint, seed_orders bigint)'
       OR (SELECT lanname FROM pg_language WHERE oid=f.prolang) <> 'sql'
       OR NOT has_function_privilege('ax_monitor',f.oid,'EXECUTE')
       OR EXISTS (SELECT 1 FROM aclexplode(coalesce(f.proacl,acldefault('f',f.proowner))) a
                  WHERE a.privilege_type='EXECUTE' AND a.grantee NOT IN (own,(SELECT oid FROM pg_roles WHERE rolname='ax_monitor'))) THEN
      RAISE EXCEPTION 'Existing helper definition or privileges differ: investigate before replacing';
    END IF;
  ELSE
    EXECUTE $definition$CREATE FUNCTION ax.tenant_order_counts()
RETURNS TABLE (tenant_id integer, orders bigint, seed_orders bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, ax AS $f$
    SELECT o.tenant_id, count(*), count(*) FILTER (WHERE o.order_id < 100000000)
      FROM ax.orders o GROUP BY o.tenant_id
$f$;
REVOKE ALL ON FUNCTION ax.tenant_order_counts() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION ax.tenant_order_counts() TO ax_monitor;
$definition$;
  END IF;
END
$guard$;
COMMIT;
