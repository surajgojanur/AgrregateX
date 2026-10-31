# Issue #34: complete health dependency repair proposal

Status: **NOT APPLIED; deployment blocked pending runtime security tests and
explicit approval.** This report supersedes the initial repair's claim that view
access alone could complete the health check. Migration 002 is already applied.

## Verified target and before evidence

Read-only investigation on 2026-10-31 at approximately 18:19 UTC independently
confirmed `round1-db`, loopback port 25560, database `aggregatex`, PostgreSQL 18.6
and installed extension 0.108.3. Database, extension and relevant schemas are
owned by `postgres`. An actual `ax_monitor` session (not `SET ROLE`) reproduces
`42501: permission denied for table pgt_dependencies`.

The monitor has table SELECT on `pgt_stream_tables`, `pgt_refresh_history` and
`stream_tables_info`; none of the seven other catalogs below has even column
SELECT. It inherits `pg_monitor`. Monitor/API/writer have no USAGE on
`pgtrickle_changes`. Eight SECURITY DEFINER functions in that private schema
already have effective monitor EXECUTE; making the schema directly accessible
therefore expands the callable surface even without granting buffer SELECT.
No exploitability of those trigger functions is claimed.

Orders total 1,002, seed orders 1,000. Per-tenant totals / seed totals:
`1:406/405, 2:201/200, 3:47/47, 4:47/47, 5:62/62, 6:43/43,
7:49/49, 8:46/46, 9:51/51, 10:50/50`.
Orders/products and all three tenant stream tables have enabled, forced RLS;
monitor has neither table nor column SELECT on these relations.

The running image ID is
`2a061b8dd6b5d184ebdcb0d40c616aeb434a13245e78f43f3c1098a1e694e737`.
Its OCI labels identify upstream trickle-labs/pg-trickle version 0.108.3 but
provide no source revision. Installed library SHA-256:
`7d22f093dc0841d06f0738f32ba93f06213279e6a66994dfe1bdda8cfa84b1bf`.
Version and library identity do **not** prove correspondence to a source commit.
The earlier investigation identified upstream release commit
`ce709f06327b4801f79fc48934bc96107b450907`; that is a release-source reference,
not a verified build provenance statement. Checkout Rust is 0.108.4.

## Complete source dependency and permission matrix

All names below are in `pgtrickle` unless qualified. The exact proposed column
allowlist is executable in migration 003; its guard independently checks column
types, extension membership, ownership and effective column privileges. Query
locations refer to the checked-out source. Installed binary equivalence remains
an acceptance gate, especially for optional paths not exercised by current data.

| Object | Query / columns actually referenced | Execution and failure behavior | Monitor BEFORE / proposed AFTER | Exposure |
|---|---|---|---|---|
| `pgt_stream_tables` | `src/monitor/health.rs::health_check`: `pgt_id,pgt_schema,pgt_name,pgt_relid,status,refresh_reason,refresh_reason_detail,needs_reinit,consecutive_errors,refresh_mode,downstream_publication_name,target_freshness_mode,freshness_deadline_ms`; also buffer, disk and publication helpers | Always queried; multiple Rust default/error paths; IMMEDIATE dependency query explicitly errors | table SELECT / unchanged | Existing access includes stored query text; proposal does not expand it |
| `stream_tables_info` | stale query selects `pgt_schema,pgt_name` with `WHERE stale`; view uses `last_refresh_at,schedule` and `parse_duration_seconds(text)` | Always; view executes with owner privileges (not security_invoker) | table SELECT / unchanged | Existing view exposes `st.*`; fingerprint pinned |
| `pgt_refresh_history` | health DVM fallback count: `was_full_fallback,start_time` | Always; Rust count fallback is zero | table SELECT / unchanged | Existing history may contain error text |
| `pgt_dependencies` | IMMEDIATE query: `pgt_id,source_relid,source_type`; buffer/disk joins; slot helper calls `StDependency::get_all()` (`src/catalog.rs`) selecting **all 14**: `pgt_id,source_relid,source_type,columns_used,cdc_mode,slot_name,decoder_confirmed_lsn,transition_started_at,cutover_target,cutover_lsn,column_snapshot,schema_fingerprint,source_stable_name,source_placement` | Always queried even with no IMMEDIATE streams. IMMEDIATE path propagates; dependency loader has Rust empty fallback | no table/column SELECT / unchanged | Schema snapshots, source topology, CDC state; isolated owner alone gets listed columns |
| `pgt_change_tracking` | `monitor/mod.rs::change_buffer_sizes`, `monitor/alert.rs::collect_slot_health_rows`, `api/release_096.rs::disk_health_rows`: `source_relid,source_stable_name,slot_name` | Always buffer/slot queries; disk branch conditional on nonzero headroom; slot query explicitly errors | none / unchanged | Source identities, buffer/slot naming |
| `pgt_scheduler_jobs` | health parallel job count: `status` | Only when parallel mode is not off; count fallback zero | none / unchanged | Only job status granted to isolated owner; no outcome text |
| `pgt_outbox_config` | attachment-owner join: `stream_table_oid,tide_outbox_name` | Always query, possibly no rows; Rust empty fallback | none / unchanged | Outbox identity |
| `pgt_window_states` | window registry query: `pgt_id,node_ordinal,spec_ordinal,status,estimated_bytes` | Always query; outputs conditional invalid-state and memory-budget rows; Rust empty fallback | none / unchanged | Window structure and memory use; no state-table rows |
| `pgt_publication_bindings` | `api/publication.rs::publication_binding_health_summary` → preflight/load binding: `pgt_id,stream_relid,publication_oid,publication_name,publication_owner_oid,expected_relation_oids` | Canonical catalog existence check then stream discovery; per-binding inspection conditional; failures become diagnostic issues, not proof of no bindings | none / unchanged | Replication membership/ownership |
| `pgt_freshness_controller_state` | freshness LEFT JOIN: `pgt_id,sla_status,p95_freshness_ms` | Query always; rows restricted to INTERVAL streams; `.ok()`/empty fallback can lose evidence | none / unchanged | Per-stream SLA evidence |
| `pg_stat_activity` | launcher and database scheduler counts, using `backend_type,datname` | Always; zero fallback | inherited pg_monitor / unchanged | Existing statistics visibility; isolated owner inherits only pg_read_all_stats |
| `pg_stat_user_tables` | buffer estimates via `relid,n_live_tup` | Always within buffer helper | system access / unchanged | Estimates, not buffer rows |
| `pg_class,pg_namespace,pg_roles` | source/buffer lookup and attachment owners; OID/name/schema/owner attributes | Always; some conditional joins | standard catalog access / unchanged | Object names and owners |
| `pg_trigger` | `ivm::ivm_triggers_ready`: source/stream trigger identity and enablement | Only IMMEDIATE sources; errors propagated | standard catalog access / unchanged | Trigger metadata |
| `pg_publication,pg_publication_rel` | publication preflight, owner/options and member OIDs | Only configured publication bindings | standard catalog access / unchanged | Publication metadata |
| `pg_replication_slots` and WAL functions | slot helper and `wal_decoder::get_slot_lag_bytes`: slot identity/activity/LSNs; `pg_current_wal_lsn`, `pg_wal_lsn_diff` | WAL/transitioning sources only; Rust lag fallback zero | inherited pg_monitor plus normal function ACLs / unchanged | Cluster replication metadata; future ACL/version review required |
| private buffer relations | `pg_total_relation_size(regclass)` using catalog OID; disk query resolves `to_regclass(format(...))` in configured private schema | Disk lookup requires schema USAGE; **no buffer SELECT required** | monitor has no schema USAGE / unchanged | Isolated owner receives schema lookup only, no buffer contents |
| builtins/GUC/shared memory | `current_setting`, formatting/size functions, worker-pool, memory, ring and freshness counters | Some checks configuration-dependent; no additional application table reads | normal builtin ACLs / unchanged | Resource and diagnostic evidence |

Rust `.ok()`, `unwrap_or_default` and `unwrap_or(0)` are evidence-loss hazards,
not guarantees that PostgreSQL permission errors will be caught: PostgreSQL ERROR
can escape through pgrx SPI. A returned OK count or absent dynamic check is not
proof of complete inspection. The proposed facade checks ACLs first, preserves
all native rows and adds UNKNOWN for missing required evidence. Runtime tests
must additionally exercise nonempty optional registries, WAL, publication and
window-budget cases; static coverage cannot certify those cases.

## Alternatives and recommendation

**A: direct column SELECT.** PostgreSQL supports column ACLs; validate with
`has_column_privilege` and actual projections, not table ACL checks alone.
Three dependency columns cover only the IMMEDIATE query. Slot diagnostics load
14 columns, and six further catalogs plus private schema lookup remain. This
approach avoids future automatic column exposure but leaks direct topology and
snapshot metadata and expands private-schema callable access.

**B: direct full-table SELECT.** Simpler but exposes unused fields, job outcome
text and future columns, and still needs schema lookup. Rejected as excessive.

**C: isolated operator facade (proposed).** Parameterless
`ax.monitor_health_check()` runs as new `ax_health_owner`, a NOLOGIN,
NOSUPERUSER, NOBYPASSRLS, NOINHERIT, NOCREATEROLE, NOCREATEDB, NOREPLICATION role.
No role can inherit it or SET ROLE to it. It receives the matrix's column ACLs,
schema USAGE and pg_read_all_stats with SET FALSE/ADMIN FALSE. Monitor receives
only EXECUTE on the facade; PUBLIC/API/writer receive nothing. Pinned search_path
and real-login checks reject role-switch impersonation. No arbitrary arguments
or user-defined SQL are executed. Native details remain operator-only and can
contain relation names or errors; this is not a public diagnostics endpoint.

This adds one function call, catalog ACL probes and bounded registry checks to
the existing native function. No source scan or refresh is introduced. Measured
latency and optional-path compatibility are NOT TESTED. The isolated owner still
has private-schema lookup and some existing PUBLIC function capabilities;
security-definer execution must be tested under hostile session settings before
deployment. This proposal is not an extension-wide security certification.

## Stale-table investigation

All three streams are ACTIVE, scheduled `1s`, configured DIFFERENTIAL, with
effective mode NO_DATA, zero consecutive errors and no stored last-error message.
Last successful histories are COMPLETED/NO_DATA, roughly 1.3–1.7 seconds apart;
individual observed refresh work takes approximately 1–2 ms. A snapshot found
day-category age 1.448 s and day-product age 1.239 s stale, while hour-category age
0.699 s was not. Earlier hour-category alone was stale; a subsequent health check
reported no stale tables. Launcher and database scheduler are both present.

The pinned installed view fingerprint is `a0db0c17e25f761c7d978515ce0cce6c`.
Its checked-in definition computes age from **last_refresh_at**, not
data_timestamp, and compares strictly with schedule duration. NO_DATA refreshes
advance last_refresh_at. The old data_timestamp alone does not explain these
flags. Scheduler interval is 500 ms, parallel/tiered scheduling enabled; a later
scheduler_load row showed pressure .020, threshold .800 and 8,147 cumulative
deferrals. One earlier sample reported scheduler_load WARN. Buffer estimates
were five rows / 163,840 bytes across five entries; these are statistics, not
an exact unconsumed-change count.

Conclusion: observed schedule overruns are transient but real under the strict
one-second health threshold. Evidence does not establish data loss, failed
refreshes or a sustained backlog. A separate scheduler/timing investigation is
needed if one-second cadence is required. No refresh, schedule adjustment or
WARN suppression belongs in this permission migration.

## Apply, rollback and acceptance gates

The exact SQL is in `003_monitor_health_dependencies.sql` and its includes.
Both apply and rollback intentionally raise an unconditional deployment hold
before changes. Do not remove it to force a live trial. Rollback explicitly
revokes only this role's allowlisted grants, drops the facade and role without
CASCADE, and preserves migration 002. Existing/drifted roles/functions abort.
Rerunning apply aborts on existing objects rather than silently changing them.
Transactions use lock and statement timeouts and before/after tenant/RLS/ACL
checks. No first-boot role script was run or changed for this unvalidated design.

Before deployment: prove installed build correspondence; exercise apply,
nonempty optional checks, missing-column revocations, actual monitor/API/writer
logins, forbidden role switches, hostile GUC/search_path, wrong targets,
definition drift and rollback on a disposable PostgreSQL 18.6/0.108.3 instance.
Then reconcile future-install role setup and deployment order with the new
backend facade call, and obtain approval for the reviewed migration. The backend
will report UNKNOWN until the facade exists; do not deploy it independently.

Disposable integration was deferred because the host had only 445 MiB free RAM,
about 1.95 GiB available and 4.45 GiB swap already used while four existing
containers were running. No extra database container was started. This remains
**NOT TESTED**, not PASS. Parser success is not runtime SQL validation.

`003_monitor_health_snapshot.sql` ran successfully read-only on the actual target.
The after-only verifier is prepared but not run because 003 is not installed.
Actual monitor column checks and a three-column `LIMIT 0` probe confirmed all
three privileges absent and the projection denied. Candidate-grant sufficiency
has not been tested live, including in temporary transactions.

No application writes, grants, revokes, role changes, RLS changes, container
restarts or manual refreshes were performed. Database workers continue their
normal commits; this is not a claim that operational catalogs stayed frozen.
Port 8093 had **no listener** during this continuation; it was not restarted or
reconfigured. Live HTTP/UI confirmation is therefore BLOCKED.

Latest fetched main is `fcb4b65`; PR #35 remains draft at `e44e988`. Work continues
on the pre-existing local branch `fix/issue34-complete-monitor-health-audit`,
preserving unrelated untracked files. The subsequent user instruction authorizes
committing and pushing for GitHub review only; it grants no deployment authority.

## Review delivery and service diagnostics

The follow-up delivery uses a separate draft PR stacked on PR #35's branch
`fix/monitor-health-view-permission`, not a rewrite of that branch. PR #35 owns
migration 002, already applied. This change owns the 003 proposal, NOT APPLIED.
Latest main `fcb4b65` adds G3 benchmark files without overlapping these edits.
Retarget/rebase the stacked PR after #35 merges; do not merge either automatically.

Mac PR #36 is owned by `shridhar618`, head `020a3c7`. Its description advocates
degrading only ERROR/CRITICAL/UNKNOWN and dismisses idle stale WARN based on
data_timestamp. Its current checked-out head's monitoring.py actually retains
`any(h["severity"] != "OK" ...)`: WARN still degrades. Thus there is a documented
policy conflict, but no current WARN-filter code difference to resolve. Preserve
WARN degradation and reconcile #36's description before integration. The installed
stale-view fingerprint and source formula use last_refresh_at.

Read-only follow-up diagnostics: `ss -ltnp` shows no 8093 listener; historical
Uvicorn PID 689077 no longer exists. The only current Uvicorn processes belong
to existing API containers on host ports 18081 and 8090. The 8093 launcher
`hackathon/app/run_local_demo.sh` directly execs host Python/Uvicorn; it does not
install a supervisor. No matching user service/unit, retained demo log/PID file,
or matching startup/shutdown journal entry was found. Kernel journal lookup
produced no accessible matching OOM record (exit 1), which does not rule out OOM.
Immediate cause: the standalone host process is no longer running. Whether it
exited normally, was killed, or failed cannot be established from retained
evidence. No service, process, port mapping or database was changed.

At the user's request **all six 003 SQL files now contain independent,
unconditional approval holds**, including the read-only snapshot/verifier and
included function/guards. They must not be executed as shipped. The earlier
successful read-only snapshot predates those additional holds. Any future
reviewed diagnostic-only revision must distinguish permission to inspect from
permission to deploy; removing these holds is not authorized by this commit.

Final pre-commit rerun: **44 tests passed in 1.722 s**, including a new test
requiring an unconditional hold in every 003 file. SQL and PL/pgSQL parsing of
all six held files passed again. Staged credential-pattern scan and whitespace
checks passed. Required `just fmt` / `just lint` remain blocked (command missing).
No source-row DML or CASCADE appears in the proposal. Guarded rollback contains
the intended DROP FUNCTION / DROP ROLE and exact privilege reversals; runtime
rollback safety is still unverified. The staged set excludes all `.env`, secret,
benchmark-result and unrelated demo-runbook files.

## Validation results from this continuation

Backend command (isolated temporary Python environment, pinned app requirements,
plus httpx2 and pglast 8.7):

```text
PYTHONPATH=hackathon/app python -m unittest discover -s hackathon/app/tests -q
Ran 43 tests in 1.723s
OK
```

This includes authentication/operator authorization, shard routing mocks,
UNKNOWN/WARN/WARNING/ERROR/empty health degradation, complete OK evidence,
incomplete/duplicate/malformed evidence, sanitized permission errors, and static
003 column allowlist/rollback/body-pin checks. These are unit/mock/static tests;
they do not execute the new security-definer function.

All six 003 files passed `pglast.parse_sql` and `parse_plpgsql` after removing
psql meta-command lines; includes were parsed separately. Python compileall and
git diff whitespace checks passed. Native repository checks run individually:

```text
SECURITY DEFINER check: 81 location(s) checked, 0 error(s).
check_privilege_boundaries: all checks passed
monitoring contract passed
```

The native SECURITY DEFINER scanner covers upstream `src/` and root `sql/`, not
the new hackathon facade; the new static tests check its pinned path and owner.
`just fmt` and then `just lint` were attempted after edits; both exited 127:
`just: command not found`. Required aggregate formatting/lint is **BLOCKED**;
individual checks above do not replace it. Rust compilation and extension E2E
were not run. No Rust source was edited.

Additional actual-login read-only checks: ax_monitor has zero SET ROLE paths to
roles with superuser/BYPASSRLS/raw-order access; ax_api has zero readable
pgtrickle catalog relations; API/writer without tenant context see zero orders.
API tenant contexts 1 and 2 see 406 and 201 orders respectively and zero foreign
tenant rows in both orders and the day-product stream. This samples two tenants
and one stream, not every tenant/stream combination. Counts rechecked at the end
remain 1,002/1,000. New-facade execution/role-switch negatives and rollback remain
NOT TESTED until disposable integration is available.
