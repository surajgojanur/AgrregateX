\set ON_ERROR_STOP on
-- REVIEW ONLY: migration 003 is NOT APPLIED and has no deployment approval.
-- This independent hold also blocks standalone includes and diagnostic scripts.
DO $review_only_hold$
BEGIN
    RAISE EXCEPTION 'DEPLOYMENT APPROVAL HOLD: migration 003 requires separate reviewed authorization; do not execute this proposal or its includes.';
END
$review_only_hold$;

DO $guard$
DECLARE
    phase text := current_setting('ax.monitor_health_phase', true);
    owner_oid oid;
    monitor_oid oid;
    diagnostic_oid oid;
    extension_oid oid;
    relation_oid oid;
    function_oid oid;
    catalog record;
    required_column record;
    column_entry record;
    protected_relation record;
    baseline jsonb;
    catalogs constant jsonb := '{
      "pgt_stream_tables": {"pgt_id":"bigint","pgt_schema":"text","pgt_name":"text","pgt_relid":"oid","status":"text","refresh_reason":"text","refresh_reason_detail":"text","needs_reinit":"boolean","consecutive_errors":"integer","refresh_mode":"text","downstream_publication_name":"text","target_freshness_mode":"text","freshness_deadline_ms":"bigint"},
      "stream_tables_info": {"pgt_schema":"text","pgt_name":"text","stale":"boolean"},
      "pgt_refresh_history": {"was_full_fallback":"boolean","start_time":"timestamp with time zone"},
      "pgt_dependencies": {"pgt_id":"bigint","source_relid":"oid","source_type":"text","columns_used":"text[]","cdc_mode":"text","slot_name":"text","decoder_confirmed_lsn":"pg_lsn","transition_started_at":"timestamp with time zone","cutover_target":"text","cutover_lsn":"pg_lsn","column_snapshot":"jsonb","schema_fingerprint":"text","source_stable_name":"text","source_placement":"text"},
      "pgt_change_tracking": {"source_relid":"oid","source_stable_name":"text","slot_name":"text"},
      "pgt_window_states": {"pgt_id":"bigint","node_ordinal":"integer","spec_ordinal":"integer","status":"text","estimated_bytes":"bigint"},
      "pgt_outbox_config": {"stream_table_oid":"oid","tide_outbox_name":"text"},
      "pgt_scheduler_jobs": {"status":"text"},
      "pgt_freshness_controller_state": {"pgt_id":"bigint","sla_status":"text","p95_freshness_ms":"double precision"},
      "pgt_publication_bindings": {"pgt_id":"bigint","stream_relid":"oid","publication_oid":"oid","publication_name":"text","publication_owner_oid":"oid","expected_relation_oids":"oid[]"}
    }';
BEGIN
    IF phase IS NULL OR phase NOT IN ('before', 'after', 'rollback_before', 'rollback_after')
       OR current_database() <> 'aggregatex' OR current_user <> 'postgres'
       OR session_user <> 'postgres'
       OR current_setting('server_version_num')::integer <> 180006 THEN
        RAISE EXCEPTION 'Wrong target, session identity, PostgreSQL version or migration phase';
    END IF;
    SELECT oid INTO owner_oid FROM pg_roles WHERE rolname = 'postgres' AND rolsuper;
    SELECT oid INTO extension_oid FROM pg_extension
     WHERE extname = 'pg_trickle' AND extversion = '0.108.3' AND extowner = owner_oid;
    IF owner_oid IS NULL OR extension_oid IS NULL
       OR (SELECT datdba FROM pg_database WHERE datname = current_database()) <> owner_oid
       OR current_setting('pg_trickle.change_buffer_schema', true) IS DISTINCT FROM 'pgtrickle_changes'
       OR current_setting('dynamic_library_path') <> '$libdir'
       OR (SELECT count(*) FROM pg_namespace WHERE nspname IN ('ax', 'pgtrickle', 'pgtrickle_changes')
                                                AND nspowner = owner_oid) <> 3 THEN
        RAISE EXCEPTION 'Unreviewed database, extension, schema ownership or library configuration';
    END IF;
    SELECT oid INTO monitor_oid FROM pg_roles
     WHERE rolname = 'ax_monitor' AND rolcanlogin AND NOT rolsuper AND NOT rolbypassrls
       AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication;
    IF monitor_oid IS NULL OR NOT pg_has_role(monitor_oid, 'pg_read_all_stats', 'USAGE')
       OR EXISTS (
           SELECT 1 FROM pg_roles candidate WHERE candidate.oid <> monitor_oid
             AND candidate.rolname NOT IN ('pg_monitor', 'pg_read_all_stats', 'pg_read_all_settings', 'pg_stat_scan_tables')
             AND (pg_has_role(monitor_oid, candidate.oid, 'SET') OR pg_has_role(monitor_oid, candidate.oid, 'USAGE'))
       ) OR EXISTS (
           SELECT 1 FROM pg_roles candidate WHERE candidate.rolcanlogin AND NOT candidate.rolsuper
             AND candidate.oid <> monitor_oid
             AND (pg_has_role(candidate.oid, monitor_oid, 'SET') OR pg_has_role(candidate.oid, monitor_oid, 'USAGE'))
       ) THEN
        RAISE EXCEPTION 'Monitor attributes or role-switch boundary differs from the reviewed baseline';
    END IF;
    IF has_schema_privilege(monitor_oid, 'pgtrickle_changes', 'USAGE')
       OR has_schema_privilege('ax_api', 'pgtrickle_changes', 'USAGE')
       OR has_schema_privilege('ax_writer', 'pgtrickle_changes', 'USAGE')
       OR EXISTS (
           SELECT 1 FROM pg_namespace namespace
           CROSS JOIN LATERAL aclexplode(COALESCE(namespace.nspacl, acldefault('n', namespace.nspowner))) acl
            WHERE namespace.nspname IN ('ax', 'pgtrickle', 'pgtrickle_changes')
              AND acl.privilege_type = 'CREATE' AND acl.grantee <> owner_oid
       ) THEN
        RAISE EXCEPTION 'Untrusted private-schema lookup or schema creation privilege';
    END IF;

    FOR protected_relation IN
        SELECT relation.oid, relation.relname, relation.relowner,
               relation.relrowsecurity, relation.relforcerowsecurity
          FROM pg_class relation JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
         WHERE (namespace.nspname = 'ax' AND (relation.relname IN ('orders', 'products')
               OR relation.oid IN (SELECT pgt_relid FROM pgtrickle.pgt_stream_tables WHERE pgt_schema = 'ax')))
            OR (namespace.nspname = 'pgtrickle_changes' AND relation.relkind IN ('r', 'p', 'v', 'm', 'f'))
    LOOP
        IF has_table_privilege(monitor_oid, protected_relation.oid,
                               'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN')
           OR has_any_column_privilege(monitor_oid, protected_relation.oid, 'SELECT,INSERT,UPDATE,REFERENCES') THEN
            RAISE EXCEPTION 'Monitor has a forbidden source, stream or change-buffer privilege';
        END IF;
    END LOOP;
    IF (SELECT count(*) FROM pg_class relation JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
         WHERE namespace.nspname = 'ax' AND relation.relname IN ('orders', 'products')
           AND relation.relowner = owner_oid AND relation.relrowsecurity AND relation.relforcerowsecurity) <> 2
       OR EXISTS (
           SELECT 1 FROM pgtrickle.pgt_stream_tables stream JOIN pg_class relation ON relation.oid = stream.pgt_relid
            WHERE stream.pgt_schema = 'ax' AND (relation.relowner <> owner_oid
                OR NOT relation.relrowsecurity OR NOT relation.relforcerowsecurity)
       ) THEN
        RAISE EXCEPTION 'Source or tenant stream ownership/FORCE RLS differs from the reviewed baseline';
    END IF;

    SELECT oid INTO diagnostic_oid FROM pg_roles WHERE rolname = 'ax_health_owner';
    SELECT procedure.oid INTO function_oid FROM pg_proc procedure JOIN pg_namespace namespace ON namespace.oid = procedure.pronamespace
     WHERE namespace.nspname = 'ax' AND procedure.proname = 'monitor_health_check';
    IF phase IN ('before', 'rollback_after') THEN
        IF diagnostic_oid IS NOT NULL OR function_oid IS NOT NULL THEN
            RAISE EXCEPTION 'Diagnostic role/function already exists; no overwrite or non-owned rollback is allowed';
        END IF;
    ELSE
        IF diagnostic_oid IS NULL OR NOT EXISTS (
            SELECT 1 FROM pg_roles WHERE oid = diagnostic_oid AND NOT rolcanlogin AND NOT rolsuper
             AND NOT rolbypassrls AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication AND NOT rolinherit
        ) OR EXISTS (SELECT 1 FROM pg_auth_members WHERE roleid = diagnostic_oid)
          OR (SELECT count(*) FROM pg_auth_members WHERE member = diagnostic_oid) <> 1
          OR NOT EXISTS (
              SELECT 1 FROM pg_auth_members WHERE member = diagnostic_oid
               AND roleid = 'pg_read_all_stats'::regrole AND grantor = owner_oid
               AND NOT admin_option AND inherit_option AND NOT set_option
          ) THEN
            RAISE EXCEPTION 'Diagnostic owner is not isolated or has unexpected membership options';
        END IF;
        IF EXISTS (
            SELECT 1 FROM pg_roles candidate WHERE NOT candidate.rolsuper AND candidate.oid <> diagnostic_oid
             AND (pg_has_role(candidate.oid, diagnostic_oid, 'SET') OR pg_has_role(candidate.oid, diagnostic_oid, 'USAGE'))
        ) OR EXISTS (
            SELECT 1 FROM pg_namespace namespace WHERE namespace.nspname IN ('ax', 'pgtrickle', 'pgtrickle_changes')
             AND has_schema_privilege(diagnostic_oid, namespace.oid, 'CREATE')
        ) THEN
            RAISE EXCEPTION 'Diagnostic-owner impersonation or schema creation is possible';
        END IF;
        FOR protected_relation IN
            SELECT relation.oid FROM pg_class relation JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
             WHERE namespace.nspname IN ('ax', 'pgtrickle_changes') AND relation.relkind IN ('r', 'p', 'v', 'm', 'f')
        LOOP
            IF has_table_privilege(diagnostic_oid, protected_relation.oid,
                                   'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN')
               OR has_any_column_privilege(diagnostic_oid, protected_relation.oid, 'SELECT,INSERT,UPDATE,REFERENCES') THEN
                RAISE EXCEPTION 'Diagnostic owner has a forbidden tenant or change-buffer privilege';
            END IF;
        END LOOP;
        IF NOT has_schema_privilege(diagnostic_oid, 'pgtrickle', 'USAGE')
           OR NOT has_schema_privilege(diagnostic_oid, 'pgtrickle_changes', 'USAGE') THEN
            RAISE EXCEPTION 'Diagnostic owner lacks required schema lookup privileges';
        END IF;
        IF function_oid IS NULL OR (SELECT count(*) FROM pg_proc procedure JOIN pg_namespace namespace ON namespace.oid = procedure.pronamespace
             WHERE namespace.nspname = 'ax' AND procedure.proname = 'monitor_health_check') <> 1
           OR NOT EXISTS (
               SELECT 1 FROM pg_proc procedure JOIN pg_language language ON language.oid = procedure.prolang
                WHERE procedure.oid = function_oid AND procedure.proowner = diagnostic_oid
                  AND procedure.prosecdef AND procedure.provolatile = 'v' AND procedure.pronargs = 0
                  AND procedure.proretset AND procedure.prorettype = 'record'::regtype
                  AND procedure.proargnames = ARRAY['check_name', 'severity', 'detail']
                  AND procedure.proallargtypes = ARRAY['text'::regtype::oid, 'text'::regtype::oid, 'text'::regtype::oid]
                  AND procedure.proargmodes = ARRAY['t', 't', 't']::"char"[]
                  AND language.lanname = 'plpgsql'
                  AND procedure.proconfig = ARRAY['search_path=pg_catalog, pg_temp', 'row_security=on']
                  AND md5(regexp_replace(procedure.prosrc, '\s+', '', 'g')) = 'eb89109f3364b5f016b2fe9eca45d7d0'
           ) OR NOT has_function_privilege(monitor_oid, function_oid, 'EXECUTE')
             OR has_function_privilege('ax_api', function_oid, 'EXECUTE')
             OR has_function_privilege('ax_writer', function_oid, 'EXECUTE')
             OR EXISTS (
                 SELECT 1 FROM pg_proc procedure
                 CROSS JOIN LATERAL aclexplode(COALESCE(procedure.proacl, acldefault('f', procedure.proowner))) acl
                  WHERE procedure.oid = function_oid
                    AND (acl.grantee NOT IN (diagnostic_oid, monitor_oid) OR acl.is_grantable
                         OR acl.privilege_type <> 'EXECUTE' OR acl.grantor <> diagnostic_oid)
             ) THEN
            RAISE EXCEPTION 'Facade definition, owner, security attributes or execute ACL differs from the reviewed version';
        END IF;
    END IF;

    FOR catalog IN SELECT key AS name, value AS columns FROM jsonb_each(catalogs)
    LOOP
        SELECT relation.oid INTO relation_oid FROM pg_class relation JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
         WHERE namespace.nspname = 'pgtrickle' AND relation.relname = catalog.name
           AND relation.relowner = owner_oid AND NOT relation.relrowsecurity AND NOT relation.relforcerowsecurity
           AND relation.relpersistence = 'p'
           AND relation.relkind = CASE WHEN catalog.name = 'stream_tables_info' THEN 'v'::"char" ELSE 'r'::"char" END
           AND EXISTS (SELECT 1 FROM pg_depend dependency WHERE dependency.classid = 'pg_class'::regclass
                        AND dependency.objid = relation.oid AND dependency.refclassid = 'pg_extension'::regclass
                        AND dependency.refobjid = extension_oid AND dependency.deptype = 'e');
        IF relation_oid IS NULL THEN
            RAISE EXCEPTION 'Unreviewed catalog type, owner, RLS or extension membership: %', catalog.name;
        END IF;
        EXECUTE format('LOCK TABLE pgtrickle.%I IN ACCESS SHARE MODE', catalog.name);
        FOR required_column IN SELECT key AS name, value AS type FROM jsonb_each_text(catalog.columns)
        LOOP
            IF NOT EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = relation_oid
                AND attname = required_column.name AND atttypid = to_regtype(required_column.type)
                AND attnum > 0 AND NOT attisdropped AND attgenerated = '') THEN
                RAISE EXCEPTION 'Unreviewed health column or type: %.%', catalog.name, required_column.name;
            END IF;
        END LOOP;
        IF catalog.name IN ('pgt_stream_tables', 'pgt_refresh_history', 'stream_tables_info') THEN
            IF NOT has_table_privilege(monitor_oid, relation_oid, 'SELECT') THEN
                RAISE EXCEPTION 'Reported baseline/migration 002 is not present';
            END IF;
        ELSIF has_any_column_privilege(monitor_oid, relation_oid, 'SELECT') THEN
            RAISE EXCEPTION 'Unexpected direct monitor dependency privileges; do not overwrite the ACL baseline';
        END IF;
        IF has_any_column_privilege('ax_api', relation_oid, 'SELECT')
           OR has_any_column_privilege('ax_writer', relation_oid, 'SELECT')
           OR EXISTS (
               SELECT 1 FROM pg_class relation
               CROSS JOIN LATERAL aclexplode(COALESCE(relation.relacl, acldefault('r', relation.relowner))) acl
                WHERE relation.oid = relation_oid AND acl.grantee = 0 AND acl.privilege_type = 'SELECT'
           ) OR EXISTS (
               SELECT 1 FROM pg_attribute attribute CROSS JOIN LATERAL aclexplode(attribute.attacl) acl
                WHERE attribute.attrelid = relation_oid AND acl.grantee = 0 AND acl.privilege_type = 'SELECT'
           ) THEN
            RAISE EXCEPTION 'Monitoring catalog access leaks to an application role or PUBLIC';
        END IF;
        IF diagnostic_oid IS NOT NULL THEN
            IF has_table_privilege(diagnostic_oid, relation_oid,
                    'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN')
               OR has_any_column_privilege(diagnostic_oid, relation_oid, 'INSERT,UPDATE,REFERENCES') THEN
                RAISE EXCEPTION 'Diagnostic owner has a non-column or write grant on %', catalog.name;
            END IF;
            FOR column_entry IN SELECT attnum, attname, attacl FROM pg_attribute
                              WHERE attrelid = relation_oid AND attnum > 0 AND NOT attisdropped
            LOOP
                IF has_column_privilege(diagnostic_oid, relation_oid, column_entry.attnum, 'SELECT')
                   IS DISTINCT FROM (catalog.columns ? column_entry.attname::text)
                   OR (catalog.columns ? column_entry.attname::text AND NOT EXISTS (
                       SELECT 1 FROM aclexplode(column_entry.attacl) acl WHERE acl.grantee = diagnostic_oid
                        AND acl.grantor = owner_oid AND acl.privilege_type = 'SELECT' AND NOT acl.is_grantable
                   )) THEN
                    RAISE EXCEPTION 'Diagnostic column privileges differ from the allowlist';
                END IF;
            END LOOP;
        END IF;
    END LOOP;

    IF NOT EXISTS (
        SELECT 1 FROM pg_class WHERE oid = 'pgtrickle.stream_tables_info'::regclass
         AND NOT ('security_invoker=true' = ANY(COALESCE(reloptions, ARRAY[]::text[])))
         AND md5(regexp_replace(pg_get_viewdef(oid, true), '\s+', '', 'g')) = 'a0db0c17e25f761c7d978515ce0cce6c'
    ) OR EXISTS (
        SELECT 1 FROM pg_rewrite rewrite JOIN pg_depend dependency ON dependency.classid = 'pg_rewrite'::regclass
          AND dependency.objid = rewrite.oid AND dependency.refclassid = 'pg_class'::regclass
         WHERE rewrite.ev_class = 'pgtrickle.stream_tables_info'::regclass
           AND dependency.refobjid NOT IN ('pgtrickle.stream_tables_info'::regclass, 'pgtrickle.pgt_stream_tables'::regclass)
    ) THEN
        RAISE EXCEPTION 'Reviewed stale view definition/dependencies changed';
    END IF;
    FOR required_column IN SELECT * FROM (VALUES
        ('pgtrickle.health_check()', 'health_check_wrapper'),
        ('pgtrickle.change_buffer_sizes()', 'change_buffer_sizes_wrapper'),
        ('pgtrickle.slot_health()', 'slot_health_wrapper'),
        ('pgtrickle.parse_duration_seconds(text)', 'parse_duration_seconds_wrapper')
    ) AS expected(signature, symbol)
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_proc procedure JOIN pg_language language ON language.oid = procedure.prolang
             WHERE procedure.oid = to_regprocedure(required_column.signature)
               AND procedure.proowner = owner_oid AND NOT procedure.prosecdef
               AND language.lanname = 'c' AND procedure.prosrc = required_column.symbol
               AND procedure.probin IN ('pg_trickle', '$libdir/pg_trickle')
               AND procedure.proconfig IS NULL
               AND EXISTS (SELECT 1 FROM pg_depend dependency WHERE dependency.classid = 'pg_proc'::regclass
                    AND dependency.objid = procedure.oid AND dependency.refclassid = 'pg_extension'::regclass
                    AND dependency.refobjid = extension_oid AND dependency.deptype = 'e')
        ) THEN
            RAISE EXCEPTION 'Unreviewed diagnostic C function: %', required_column.signature;
        END IF;
    END LOOP;

    SELECT jsonb_build_object(
        'relations', (SELECT jsonb_agg(jsonb_build_array(relation.oid, relation.relowner, relation.relacl,
                    relation.relrowsecurity, relation.relforcerowsecurity) ORDER BY relation.oid)
            FROM pg_class relation JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace WHERE namespace.nspname = 'ax'),
        'columns', (SELECT jsonb_agg(jsonb_build_array(attribute.attrelid, attribute.attnum, attribute.attname,
                    attribute.atttypid, attribute.attnotnull, attribute.attgenerated, attribute.attidentity, attribute.attacl)
                    ORDER BY attribute.attrelid, attribute.attnum)
            FROM pg_attribute attribute JOIN pg_class relation ON relation.oid = attribute.attrelid
            JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace WHERE namespace.nspname = 'ax'),
        'policies', (SELECT jsonb_agg(to_jsonb(policy) ORDER BY policy.oid) FROM pg_policy policy
            JOIN pg_class relation ON relation.oid = policy.polrelid JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = 'ax'),
        'roles', (SELECT jsonb_agg(jsonb_build_array(oid, rolsuper, rolinherit, rolcreaterole, rolcreatedb,
                   rolcanlogin, rolreplication, rolbypassrls) ORDER BY oid)
            FROM pg_roles WHERE rolname IN ('ax_monitor', 'ax_api', 'ax_writer')),
        'memberships', (SELECT jsonb_agg(to_jsonb(membership) ORDER BY membership.oid) FROM pg_auth_members membership
            WHERE membership.member IN (SELECT oid FROM pg_roles WHERE rolname IN ('ax_monitor', 'ax_api', 'ax_writer')))
    ) INTO baseline;
    IF phase IN ('before', 'rollback_before') THEN
        PERFORM set_config('ax.monitor_health_baseline', baseline::text, true);
    ELSIF current_setting('ax.monitor_health_baseline', true)::jsonb IS DISTINCT FROM baseline THEN
        RAISE EXCEPTION 'Tenant schemas, ACLs, RLS policies or application roles changed during the transaction';
    END IF;
END
$guard$;
