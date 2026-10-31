# Issue #34 — pg_trickle health-check permission (least-privilege repair)

> Historical migration-002 plan: 002 has since been applied, but did not repair
> the complete health check. Follow the [dependency audit](MONITOR_HEALTH_DEPENDENCIES.md)
> for current evidence and the blocked migration-003 proposal. Do not reapply 002
> or infer deployment authorization from this historical runbook.

**Status:** Migration PR only. **NOT APPLIED to the existing Fedora database.** Running any SQL that changes `aggregatex` needs explicit human approval after comparing the diagnostics to this plan. The existing `round1-db` and localhost `8093` dashboard must remain running and unmodified until approval.

## Root cause supported by the code and recorded Fedora observation

`ax_monitor` connects through a dedicated non-superuser, `NOBYPASSRLS` monitor connection pool. `hackathon/sql/25_app_roles.sql` originally granted the role `SELECT` on `pgtrickle.pgt_stream_tables` and `pgt_refresh_history`, but **not** on `pgtrickle.stream_tables_info`.

The upstream `pgtrickle.health_check()` function reads `pgtrickle.stream_tables_info` for stale tables. The recorded Fedora call through `ax_monitor` failed with `permission denied for view stream_tables_info`; `engine.snapshot` reports this as `UNKNOWN` and `monitoring.collect_shards` correctly marks the shard degraded. A successful `/api/health` or `/api/shards` liveness response does not contradict a failed deeper health check.

The extension view in the checked-in source is `SELECT st.*, ... FROM pgtrickle.pgt_stream_tables st`; it contains catalog metadata, including **stored defining SQL**, so it is not suitable for a general application/tenant role. Only `ax_monitor` receives view access here. It is **not** a grant to `ax.orders`, `ax.products`, or the tenant stream-table rows. The installed `pg_trickle` version and view must still be checked independently.

## Guarded change

* `hackathon/sql/25_app_roles.sql` grants the view to `ax_monitor` on **new** installations.
* `hackathon/sql/migrations/002_monitor_health_view.sql` is the **explicit/manual** migration for the already initialized Fedora database; it requires DB=`aggregatex`, PostgreSQL 18.6, migrating as trusted `postgres`, exactly installed `pg_trickle 0.108.3`, the reviewed view-definition fingerprint and dependency allowlist, unchanged non-superuser monitor role and negative raw-fact permissions (including no `SET ROLE` path to source/elevated roles). SQL runs in one transaction with 2s lock and 10s statement timeouts, checks postconditions, and commits only the view-specific `GRANT SELECT`.
* `002_monitor_health_view_verify.sql` verifies as the **real monitor login** using read-only SQL, not a superuser pretending to be the monitor.
* `002_monitor_health_view_rollback.sql` is a manual, guarded `REVOKE SELECT`; use ONLY if pre-migration effective view access was absent. An already-present or inherited grant must not be removed casually.

No extension SQL, superuser powers, RLS, raw tenant privileges, source rows, stream tables, seeds or Docker objects are modified.

## Step 1: Diagnostics FIRST (read-only)

Target the host **127.0.0.1:25560**, database **aggregatex**, after checking that it still maps to the intended `round1-db`. Do not pass passwords on the command line; use securely configured `PGPASSFILE` (`0600`) or normal interactive password prompts.

Before requesting approval, collect the following, run as the intended trusted database operator in a read-only transaction:

```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout = '2s';
SELECT current_database(), current_user,
       (SELECT extversion FROM pg_extension WHERE extname = 'pg_trickle') AS pg_trickle_version;
SELECT rolname, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole, rolinherit, rolcanlogin
  FROM pg_roles WHERE rolname IN ('postgres', 'ax_monitor');
SELECT pg_get_userbyid(roleid) AS granted_role, admin_option
  FROM pg_auth_members WHERE member = 'ax_monitor'::regrole ORDER BY 1;
SELECT r.rolname, r.rolsuper, r.rolbypassrls,
       pg_has_role('ax_monitor', r.oid, 'SET') AS monitor_can_set_role
  FROM pg_roles r
 WHERE r.rolsuper OR r.rolbypassrls
    OR has_table_privilege(r.oid, 'ax.orders', 'SELECT')
    OR has_table_privilege(r.oid, 'ax.products', 'SELECT');
SELECT n.nspname, c.relname, c.relkind, c.reloptions,
       pg_get_userbyid(c.relowner) AS view_owner,
       pg_get_viewdef(c.oid, true) AS view_definition
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'pgtrickle' AND c.relname = 'stream_tables_info';
SELECT has_schema_privilege('ax_monitor','pgtrickle','USAGE') AS monitor_schema,
       has_table_privilege('ax_monitor','pgtrickle.pgt_stream_tables','SELECT') AS monitor_catalog,
       has_table_privilege('ax_monitor','pgtrickle.stream_tables_info','SELECT') AS monitor_view_before,
       has_function_privilege('ax_monitor','pgtrickle.parse_duration_seconds(text)','EXECUTE') AS duration_function,
       has_function_privilege('ax_monitor','pgtrickle.health_check()','EXECUTE') AS health_execute,
       has_table_privilege('ax_monitor','ax.orders','SELECT') AS raw_orders,
       has_table_privilege('ax_monitor','ax.products','SELECT') AS raw_products;
ROLLBACK;
```

Do **not** publish credentials, private query definitions, connection strings or a full database dump to GitHub. Share only redacted ACL/owner/role/version verdicts and sanitized errors. If any diagnostic differs, **STOP**; don't weaken the migration guard to force it to pass.

## Step 2: Human-approved migration (not automated)

Only after reviewing Step 1 and explicitly approving this exact single-view grant:

```sh
cd /home/god/Documents/github/AgrregateX
# Confirm the SQL diff and exact target; do not run all 25_app_roles.sql.
# Provide credentials via a secure PGPASSFILE or interactive password prompt.
psql -h 127.0.0.1 -p 25560 -U postgres -d aggregatex \
  -X -v ON_ERROR_STOP=1 -f hackathon/sql/migrations/002_monitor_health_view.sql
```

`psql` exit 0 means the guarded grant committed; it does **not** prove `health_check()` returns a healthy diagnosis.

## Step 3: Real monitoring-role verification (read-only)

```sh
psql -h 127.0.0.1 -p 25560 -U ax_monitor -d aggregatex \
  -X -v ON_ERROR_STOP=1 -f hackathon/sql/migrations/002_monitor_health_view_verify.sql
```

Confirm the function now executes without `permission denied` and outputs real `OK/WARN/ERROR` results. An actual WARN or ERROR must remain visible as `degraded`. Check that the role cannot read `ax.orders` or `ax.products` and that no DML/RLS permissions changed. Any unexpected permission error must be diagnosed separately rather than adding broad grants.

Then, **without restarting 8093**, allow the 15-second monitoring cache to expire and issue a bounded, read-only GET `http://127.0.0.1:8093/api/monitoring` plus a Chromium check of `/app#/monitoring`. Record the **actual** state; do not force `healthy`. Also recheck `/api/health`, `/api/shards` and unchanged per-tenant counts 1,002/1,000 **only if they still match reality at test time**.

## Step 4: Rollback (manual, only if indicated)

If Step 3 exposes a security regression or unwanted catalog exposure, and the **before** snapshot showed no monitor view access, use the guarded rollback file as the trusted operator:

```sh
psql -h 127.0.0.1 -p 25560 -U postgres -d aggregatex \
  -X -v ON_ERROR_STOP=1 -f hackathon/sql/migrations/002_monitor_health_view_rollback.sql
```

Recheck the effective ACL and live monitoring status; an `UNKNOWN` after rollback is expected. Rollback must not affect fact rows or RLS.

## Acceptance gates

1. The only ACL delta is `ax_monitor` receiving `SELECT` on the extension metadata view; no `PUBLIC`, `ax_api`, or `ax_writer` grants.
2. `ax_monitor` remains `NOSUPERUSER` and `NOBYPASSRLS`, with **no raw `ax.orders` or `ax.products` SELECT**.
3. Real `ax_monitor` executes `pgtrickle.health_check()` without permission errors, the monitoring page no longer shows this specific `UNKNOWN`, and genuine health warnings still degrade it.
4. `round1-db` source data, existing single `DEFAULT` shard counts, RLS, other pages, containers and port 8093 are preserved.
5. If real Fedora connection, human approval, or suitable privileges are unavailable, label the migration **NOT APPLIED / BLOCKED** rather than saying it fixed the live application.

**Version note:** the checked-in source tree may be ahead of installed v0.108.3. The hard guard intentionally targets only the observed PostgreSQL 18.6 / pg_trickle 0.108.3 pair and the SHA-128 fingerprint of its whitespace-normalized `pg_get_viewdef`. A mismatch stops the migration; it is not a reason to weaken the check. New installations with a different PostgreSQL or extension version require a fresh view/ACL review first.
