\pset format unaligned
\pset tuples_only on
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT 'role', rolname, rolsuper, rolinherit, rolcreaterole, rolcreatedb, rolcanlogin, rolreplication, rolbypassrls FROM pg_roles WHERE rolname !~ '^pg_' ORDER BY 2;
SELECT 'member', r.rolname, m.rolname, a.admin_option, a.inherit_option, a.set_option, g.rolname FROM pg_auth_members a JOIN pg_roles r ON r.oid=a.roleid JOIN pg_roles m ON m.oid=a.member JOIN pg_roles g ON g.oid=a.grantor ORDER BY 2,3;
SELECT 'nsp', nspname, pg_get_userbyid(nspowner), nspacl FROM pg_namespace WHERE nspname !~ '^pg_' AND nspname <> 'information_schema' ORDER BY 2;
SELECT 'rel', n.nspname, c.relname, c.relkind, pg_get_userbyid(c.relowner), c.relacl, c.relrowsecurity, c.relforcerowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('ax','pgtrickle','pgtrickle_changes') AND c.relkind IN ('r','p','v','m','f','S') ORDER BY 2,3;
SELECT 'col', n.nspname, c.relname, a.attname, a.attacl FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('ax','pgtrickle','pgtrickle_changes') AND a.attacl IS NOT NULL ORDER BY 2,3,4;
SELECT 'fn', n.nspname, p.oid::regprocedure::text, pg_get_userbyid(p.proowner), p.prosecdef, p.proconfig, p.proacl, md5(p.prosrc) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname IN ('ax','pgtrickle','pgtrickle_changes') ORDER BY 2,3;
SELECT 'policy', polrelid::regclass, polname, polcmd, polroles::regrole[], pg_get_expr(polqual, polrelid), pg_get_expr(polwithcheck, polrelid) FROM pg_policy ORDER BY 2,3;
SELECT 'defacl', defaclrole::regrole, defaclnamespace, defaclobjtype, defaclacl FROM pg_default_acl ORDER BY 2,3,4;
SELECT 'db', datname, datacl FROM pg_database WHERE datname = current_database();
SELECT 'data', tenant_id, count(*), sum(line_cents), md5(string_agg(order_id::text||status, ',' ORDER BY order_id)) FROM ax.orders GROUP BY 2 ORDER BY 2;
COMMIT;
