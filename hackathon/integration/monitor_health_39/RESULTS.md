# Issue #39: independent validation of migration 003 (PR #38 monitor-health facade)

**Recommendation: `SECURITY READY FOR HUMAN REVIEW`, with two MEDIUM items to fix before any deployment.**
This is **not** deployment approval. Fedora, `round1-db`, `:25560` and the user's demo stack were not touched.
PR #38 and #35 are not merged, and no PR file was edited.

## Environment
| Item | Value |
|---|---|
| Host | Apple M1, 8 GB RAM, Docker VM 3.8 GiB; swap 7–9 GiB used; 22 GiB disk free |
| Target | **fresh** disposable Compose project `ax-mh39`, `127.0.0.1:25590`, its own volume, db service only, `mem_limit 1g`; built from `hackathon/compose.yaml` at PR #38 head `daefdd6` (stacked on #35 `e44e988`) with a ports-only override; 10k seed orders |
| Image | `ghcr.io/trickle-labs/pg_trickle:latest` = `sha256:94344bb98995b19c826f939739672481abaab8c25710e3910b48bdb7cf5b3b8d` (created 2026-10-06) |
| Engine | PostgreSQL `180006`, pg_trickle `0.108.3`, `parallel_refresh_mode=on`, `disk_headroom_mb=1024`, `scheduler_interval_ms=500`, schedule `1s` |
| Approval | the user explicitly approved this exact target, plus hold removal in a scratch copy outside git (2026-11-01) |

**Holds.** The six `003_*.sql` files were copied to a scratch directory. Only the six `DO $review_only_hold$` / `$deployment_blocked$` / `$rollback_blocked$` blocks were removed (5 lines each, verified by diff). The function body is byte-identical, so the guard's md5 pin still applies. The hold-free copies are **not** committed.

## Results
| # | Test | Result | Evidence |
|---|---|---|---|
| B1 | Before snapshot: roles, memberships, schema/table/column/function ACLs, policies, default ACLs, database ACL, per-tenant data checksums (`snap.sql`) + the PR's `003_monitor_health_snapshot.sql` | PASS | `evidence/snap-before.txt`, `evidence/pr-snapshot-before.txt` |
| B6 | **First boot without 003:** PR #38 `read_health` as the real `ax_monitor` returns `monitor_contract UNKNOWN (SQLSTATE 42883)`, so B-5 is **degraded** | **FAIL (MED-1)**: every fresh install is permanently degraded once the #38 backend merges | `evidence/b6-pre003-read_health.json` |
| B2 | Apply `003_monitor_health_dependencies.sql` (002 baseline present from `25_app_roles.sql`): guards `before` and `after` pass | PASS (exit 0) | `evidence/b2-apply.txt` |
| B2 | Re-apply is refused ("already exists; no overwrite"), with no change | PASS (exit 3) | console |
| B3 | `003_monitor_health_verify.sql` as the real `ax_monitor` login | PASS: 23 rows, `monitor_contract OK` | `evidence/b3-verify.txt` |
| B3 | **Permission-negative probes as `ax_monitor`** (all 42501): `ax.orders/products/customers`; the 3 stream tables; the 7 private catalogs; a `pgtrickle_changes.changes_*` buffer; native `health_check()` and `change_buffer_sizes()`; `SET ROLE` / `SET SESSION AUTHORIZATION ax_health_owner`; `CREATE OR REPLACE` / `ALTER … SECURITY INVOKER` / `ALTER … OWNER` on the facade | PASS 21/21 | `evidence/b3-probes.json` |
| B3 | `ax_monitor` `GRANT EXECUTE … TO ax_api` (no grant option): `ax_api` still has no EXECUTE | PASS | same |
| B3 | Facade EXECUTE by `ax_api`, `ax_writer` and a fresh unrelated login → 42501 | PASS 3/3 | same |
| B3 | A superuser calling the facade is refused by the `session_user` check (by design) | PASS (42501) | same |
| B3 | **Hostile search_path:** temp `pgt_stream_tables` with a fake ERROR row + temp `pg_stat_activity` + `search_path = pg_temp, pgtrickle, ax, public`. Output identical to baseline (`error_tables OK`, `scheduler_running 1 worker`) | PASS (manual). The JSON row shows FAIL because of a **harness bug** (it compared dict keys), fixed in `b3_probes.py` | `evidence/b3-hostile-manual.txt` |
| B3 | GUC tampering: `parallel_refresh_mode`, `change_buffer_schema` → **refused (42501)**; `row_security=off` → no effect; `disk_headroom_mb=0` → **allowed**, `disk_forecast` becomes "disabled/OK" in that session only | PASS / **LOW-1** | `evidence/b3-probes.json` |
| B3 | `statement_timeout=1ms` → 57014 propagates; the app reduces it to SQLSTATE only | PASS | same |
| B4 | **Parity idle:** facade (`ax_monitor`) vs native `health_check()` (postgres), concurrent, every 0.2 s for 60 s: 279 samples, contract OK 279/279, severity mismatches **1** (`stale_tables` timing) | PASS | `evidence/b4-idle.json` |
| B4 | **Parity under load:** pgbench inserts at 100 TPS (7,553 transactions, 0 failed; 133 DIFFERENTIAL + 6 FULL refreshes): 270 samples, contract OK 270/270, mismatches **0**; facade p50 9.4 ms / p95 70.5 ms / max 265 ms | PASS | `evidence/b4-load.json`, `evidence/b4-load-pgbench.txt` |
| B4 | Paths not exercised: IMMEDIATE mode, WAL CDC/slots, publications, window state, freshness `INTERVAL` targets, disk-headroom breach. Upstream silent-default paths (`SpiError` → empty/0 → OK) remain possible | **NOT TESTED** | see #39 Phase A |
| B5 | Live B-5 state after 003: `stale_tables` WARN + `dvm_fallbacks` WARN (6 FULL fallbacks from the load) → **degraded** (6/6 samples). WARN degrades, as #36/#38 require | PASS | `evidence/b5-post003-read_health.jsonl` |
| B5 | **WARN cadence:** `stale = now() - last_refresh_at > schedule (1 s)`, while measured refresh starts are **1.47–1.49 s apart on average (max 2.08 s)**. `stale_tables` is non-OK **81 %** of samples idle and **89 %** under load, in the facade and native alike. Not a 003 defect, but B-5 is "degraded" most of the time at the 1 s schedule | **FINDING (MED-2)** | `evidence/b4-*.json` |
| B5 | OK / WARNING / ERROR state mapping | unit tests only (15/15 PASS); not induced live | PR #38 tests |
| B7 | Guarded rollback `003_monitor_health_dependencies_rollback.sql`: guards `rollback_before` and `rollback_after` pass | PASS (exit 0) | `evidence/b7-rollback.txt` |
| B7 | **Exact restore:** roles, memberships, schema/table/column/function ACLs, policies, default and database ACLs identical to before (289 lines, `diff` empty). Seed data (order_id < 1e8) checksums identical for all 10 tenants; the only new rows are the 7,553 pgbench test rows | PASS | `evidence/snap-after-rollback.txt`, `evidence/data-seed-after.txt` |
| B7 | Rollback re-run is refused. Its message ("Diagnostic owner is not isolated…") is misleading when the role is absent | PASS / **LOW-2** | console |
| B7 | After rollback, the #38 backend falls back to `monitor_contract UNKNOWN (42883)`: degraded and fail-closed, with no privileged fallback | PASS | `evidence/b7-post-rollback-read_health.json` |
| B6 | HTTP endpoint `/api/monitoring` with the #38 backend | **NOT TESTED** (API image not built on the memory-constrained Mac; `read_health` was exercised directly as `ax_monitor`) | |

## Findings and proposed minimal fixes
- **MED-1: fresh installs never get the facade** (B6, live).
  - No first-boot step creates it (`app/db/init.sh`, `sql/25_app_roles.sql`).
  - So after the #38 backend merges, every new stack (demo, sharded, scale, Fedora judge demo) is permanently degraded.
  - *Fix:* a reviewed first-boot provisioning file with the same body, owner and ACL, run by `init.sh`. Keep the upgrade migration's holds.
- **MED-2: the stale threshold is tighter than the achievable refresh cadence.**
  - With a `1s` schedule, B-5 is degraded 81–89 % of the time.
  - *Fix options:* a `2s` schedule for the demo (trades freshness), or an upstream tolerance of schedule + `scheduler_interval_ms`. Do **not** filter WARN.
- **MED (Phase A): provenance.**
  - `:latest` is a mutable tag, while the repo source is 0.108.4 against an installed 0.108.3.
  - *Fix:* pin images by digest and review the upstream 0.108.3 source.
- **LOW-1:** `ax_monitor` can `SET pg_trickle.disk_headroom_mb = 0` and blind `disk_forecast` for its own session. Impact is limited to the monitor's own view. *Optional fix:* the facade requires `disk_headroom_mb` > 0, or reads `reset_val`.
- **LOW-2:** rollback re-run error text is misleading. *Optional fix:* a distinct "nothing to roll back" message.
- **LOW (Phase A):** the EXCEPTION handler covers 4 SQLSTATEs; the `pgt_dependencies` column allowlist may be broader than needed.

## Reproduce
- **Scripts:** `snap.sql` (read-only snapshot, run as postgres), `probe_health.py` (PR #38 `read_health` as `ax_monitor`), `b3_probes.py` (negative/hostile probes), `b4_parity.py` (parity and WARN rate).
- **Credentials:** they use the repo's documented local demo defaults and port 25590. Run them only against a disposable stack.
