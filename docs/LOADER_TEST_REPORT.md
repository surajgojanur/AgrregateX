# Loader test report — Phase 01A

All results below are from **bounded runs on a disposable local cluster**. **No 10M load was run.** The
Phase 00 Fedora database and the pg_trickle demo were not touched (they are not reachable from this
machine).

## Environment

| Item | Value |
|---|---|
| Host | macOS (Apple silicon, 8 cores, 8 GiB RAM), ~11 GiB free disk |
| PostgreSQL | 17.6 (Homebrew), throwaway cluster on 127.0.0.1:25499 |
| Settings | Same as compose.yaml: `shared_buffers=128MB work_mem=4MB maintenance_work_mem=64MB max_wal_size=2GB max_parallel_workers_per_gather=0 track_commit_timestamp=on` |
| Not reproduced | **No container CPU/memory limits** (Phase 00: DB 1.5 CPU / 1.8 GiB); PostgreSQL 18.6; Fedora i3-1115G4; Podman |
| Schema | `database/schema.sql` from main 84aab53, unmodified, applied to each fresh test database |
| Client | Python 3.13, psycopg 3.2.3 |

The differences above mean absolute timings will be slower on the target host. The ratios and correctness
results are the transferable evidence.

## Automated tests — 14/14 passed

```
LOADER_TEST_ADMIN_DSN=postgresql://agrregatex_owner@127.0.0.1:25499/postgres \
  python -m unittest discover -s generator/tests -v
Ran 14 tests in 48.2s — OK
```

Each test creates its own database from `database/schema.sql` and drops it afterwards.

| Test | What it proves |
|---|---|
| `full_load_reconciles_and_is_isolated_from_api` | 9k rows / 7 tenants / 9 batches load; ids unique; stage freed; trigger re-enabled; full reconciliation 0 mismatches; uneven tenants (tenant 1 > 35%); API role is denied on `loader.*` |
| `rows_match_phase00_legacy_formula` | Staged rows equal the Phase 00 `load.py` SQL row for row (`EXCEPT ALL` in both directions = 0) |
| `interrupt_crash_resume_is_deterministic` | Injected stop after 3 batches → 3 checkpoints / 3,000 rows, 0 visible. Then a hard `os._exit` *inside* an open batch transaction → that batch rolled back (4 checkpoints, 4,000 rows, deltas Σn = 4,000). Resume → source fingerprint and **both rollup tables byte-identical** to an uninterrupted reference load |
| `sigkill_mid_staging_then_resume` | `kill -9` during a 300k-row load → stage = checkpoints × batch size, 0 visible, resume → 300,000 unique rows, reconciled |
| `sigterm_stops_at_batch_boundary` | SIGTERM → exit 130 at a batch boundary; resume completes, reconciled |
| `retries_are_idempotent_and_tampering_is_rejected` | Re-running `load`/`stage`/`activate` after activation changes nothing. A foreign staged row in an uncheckpointed range → CONFLICT (exit 3), rollback, deltas unchanged; `abort` + re-load works |
| `conflicting_spec_and_concurrent_loader_refused` | A different spec while a run is open is refused; a second loader process is refused, with the lock holder reported |
| `full_scale_is_gated` | 10M refused without both the flag and the env gate, also through the `load.py 10000000 100` wrapper |
| `failed_activation_rolls_back_completely` | Failure injected after insert + merge, before commit → orders/rollups/tenants unchanged, trigger enabled, run still `verified`, stage intact; retry succeeds |
| `api_writes_before_activation_and_atomic_visibility_for_readers` | Pre-existing API rows plus UPDATE (status, time shift) and DELETE between stage and activation → exact rollups after the additive merge. A concurrent reader polling `(count(orders), Σn daily, Σn hourly)` saw **only** the old or the new triple (both observed, so it was never blocked). Writes after activation keep rollups exact |
| `prefix_extension_and_provenance_check` | 4k/5 tenants extended to 10k/9 tenants, reconciled. A modified prefix row → CONFLICT, nothing changed; `--prefix-check count` accepts it; a wrong prefix size → CONFLICT |
| `rebuild_index_mode` | `--mode rebuild-index` recreates `orders_time`, reconciled |
| `rebuild_rollups_repairs_drift_and_preserves_security` | Injected drift (one row +1, one row deleted) detected (exit 1), repaired by shadow swap; RLS, policy, API grant and `_pkey` names preserved; a pre-existing pooled session's cached trigger writes to the new tables; RLS still isolates tenants |
| `manifest_interface` | View and CLI agree; field values correct; validation recorded with `after_load` |

## Bounded 1M measurement (1,000,000 rows / 10 tenants / 50k batches)

The run was killed with **SIGKILL after 8 committed batches** (400,000 staged rows, 0 rows visible in
`orders`) and resumed with the identical command, adding `--verify-rollups`.

### Stage (per batch, all 20)

| Metric | Value |
|---|---|
| Batch time avg / min / max | 715 / 535 / 895 ms (~70k rows/s) |
| WAL per batch (avg) | 27.5 MB (≈ 550 B/row) |
| Resume invocation | 12 remaining batches in 7.96 s; 0 checkpoints triggered |
| Loader backend memory (between batches) | ≤ 2.5 MB |
| Python peak RSS | 51 MB (constant; rows are generated server-side) |
| Peak stage footprint | stage 107 MB (84 heap + 22 index) + deltas 79 MB |

### Verify / activate / finalize

| Step | Seconds |
|---|---|
| verify-stage (full fingerprint) | 0.62 |
| **activation transaction** (incremental) | **12.75** |
| — insert 1M into indexed `orders` | 10.00 |
| — merge daily / hourly deltas | 0.31 / 1.41 |
| — truncate stage | 1.02 |
| Activation WAL | 448 MB, 0 checkpoints |
| finalize (VACUUM ANALYZE) | 0.24 |
| verify-rollups (full reconciliation) | 1.56, **0 / 0 mismatches** |
| Whole resume invocation | 23.1 s |

Result: `orders` 211 MB (101 MB heap + 110 MB index), `daily_product` 13.0 MB, `hourly_category` 49.9 MB,
database 283 MB. Tenant counts **401,067 / 199,325 / 50,256…**, the same as the Phase 00 audit.

Phase 00 reported `orders` at 733 MB for the same 1M rows. That is plausibly bloat from the rolled-back 10M
attempt (dead tuples), but this was **not verified**.

### Activation alternatives (same 1M stage, each run in a transaction and rolled back)

| Variant | INSERT time | Decision |
|---|---|---|
| Trigger off, `ORDER BY tenant_id, ordered_at`, FK on (**default**) | 14.9 s | chosen |
| Same, unordered | 20.6 s | ordering 28% faster |
| `session_replication_role=replica` (no FK, no trigger) | 12.1 s | only 19% faster; unsafe, rejected |
| Trigger off, `orders_time` dropped | 14.5 s | about the same, but would block readers |
| **Per-row rollup trigger left on** | **78.8 s** | 5.3× slower; this is what staged deltas avoid |
| `--mode rebuild-index` full activation | 13.45 s (vs 12.75 s) | no gain at 1M |

### Prefix extension (Phase 00-equivalent 1M baseline → 1.25M / 20 tenants)

The env gate was set for this run on the disposable cluster only.

| Step | Seconds |
|---|---|
| Stage 250k rows | 3.6 |
| Prefix fingerprint check (generate 1M + scan existing) | 1.64 |
| Insert 250k rows | 6.31 (≈ 25 µs/row vs 10 µs/row into an empty table) |
| Activation transaction | 13.9 |
| verify-rollups | 2.0, passed; 1,250,000 rows, 20 tenants |

## 10M projection — UNVERIFIED

This is a linear extrapolation from the local runs. It will be slower on the target host.

| Quantity | Estimate | Note |
|---|---|---|
| Stage time | ~2.5 min local | resumable, and the API is unaffected apart from I/O |
| Stage WAL | ~5.5 GB, spread over many commits | |
| Activation transaction | ≥ 2–4 min local | per-row insert cost already rose 2.5× from 0 → 1M existing rows; index sizes ≫ `shared_buffers` |
| Activation WAL | ≥ 4.5 GB in one transaction | multiple checkpoints |
| Disk peak (fresh 10M) | stage ~1.1 GB + deltas ~0.7 GB + orders ~2.1 GB + WAL ≤ ~4.5 GB | the 30 GiB precondition is conservative |
| Writes blocked | the whole activation transaction | reads continue |

These need to be measured on the target host in the gated 10M run (resource monitor: cgroup RAM, CPU,
WAL, checkpoints, locks).

## Reproduce

```bash
python3 -m venv .venv && .venv/bin/pip install 'psycopg[binary]==3.2.3'
initdb -D /tmp/pgl -U agrregatex_owner --auth=trust
pg_ctl -D /tmp/pgl -o "-p 25499 -c shared_buffers=128MB -c work_mem=4MB -c maintenance_work_mem=64MB -c max_wal_size=2GB -c max_parallel_workers_per_gather=0" start
LOADER_TEST_ADMIN_DSN=postgresql://agrregatex_owner@127.0.0.1:25499/postgres .venv/bin/python -m unittest discover -s generator/tests -v

# 1M kill/resume (fresh DB with database/schema.sql and role agrregatex_api)
export ADMIN_DATABASE_URL=postgresql://agrregatex_owner@127.0.0.1:25499/m1
.venv/bin/python generator/loader.py load --rows 1000000 --tenants 10 & sleep 8; kill -9 %1
.venv/bin/python generator/loader.py load --rows 1000000 --tenants 10 --verify-rollups
```
