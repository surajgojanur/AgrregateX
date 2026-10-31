# Loader design — Phase 01A (resumable bulk loading, consistent rollups)

Owner: Claude Opus (Developer A). Code: `generator/loader.py`, migrations `generator/migrations/*.sql`,
tests `generator/tests/test_loader.py`. Evidence: `docs/LOADER_TEST_REPORT.md`.

**Dataset status:** representative only. The official organizer generator/schema has not been supplied;
compatibility is **NOT VERIFIED**. Generator `representative-v1` reproduces the Phase 00 `generator/load.py`
row formula exactly (tested row-by-row; the 1M/10-tenant output reproduces the Phase 00 tenant counts
401,067 / 199,325 / …).

## Problems with the Phase 00 loader

| Phase 00 behaviour | Consequence |
|---|---|
| One outer transaction around all 100k-row batches, index rebuild and rollup build | Nothing durable until the very end; an interruption at minute N throws away N minutes of work; long-lived locks and a long rollback |
| `ACCESS EXCLUSIVE` on `orders` for the whole load | API reads blocked for the whole load |
| Full-source `GROUP BY` rebuild of both rollups | Cost grows with the whole table, not with the rows added; this is where the 10M attempt was cancelled |
| Resume by "max id" only, no checkpoints | No proof that a partially written range is complete or not duplicated |

## Design

```
plan ──► stage (N independent batch txns) ──► verify-stage ──► activate (1 txn) ──► finalize
          │ each commit = rows + rollup deltas + checkpoint    │ readers keep the old snapshot
          └ nothing visible to the API                         └ source + rollups switch in one commit
```

### Deterministic identity

* **Run identity** `run_id = 'r' + sha256(spec)[:16]` over `{generator, seed, rows, tenants, prefix_rows,
  prefix_tenants, batch_size}`. Re-issuing the same command finds the same run, so it resumes instead of
  creating a duplicate run. A different spec is refused while a run is open (unique partial index
  `runs_one_open`).
* **Row identity** ordinal `i` ↦ `orders.id = -i`. Each row is a pure function of `(generator, seed, tenants, i)`.
  Bulk ids are negative and API ids are positive (the Phase 00 convention), so they never collide.
* **Batch identity** batch `b` covers ordinals `first + b·B … min(last, first + (b+1)·B − 1)`.

### Stage (resumable, idempotent)

Each batch runs as one transaction, executed as a single SQL statement on the server (no rows held in Python):

1. `SELECT … FROM loader.runs FOR UPDATE` serialises with any other session, then the checkpoint is
   re-checked under that lock. If the batch is already committed, it is skipped.
2. Generate the ordinal range, insert it into `loader.stage_orders` (`ON CONFLICT DO NOTHING`), and add the
   batch's signed rollup deltas into `loader.delta_daily` / `loader.delta_hourly`.
3. If fewer rows were inserted than generated, staging was modified outside the loader. The loader raises
   **CONFLICT**, the transaction rolls back and nothing changes.
4. Insert the checkpoint row (`loader.batches`: row count, order-independent fingerprint, units, cents,
   group counts, elapsed time, WAL bytes) and commit.

A checkpoint exists **iff** the batch's rows and deltas exist, so a crash can never leave a half-batch or
double-counted deltas.

Interruption semantics:

| Event | Effect | Recovery |
|---|---|---|
| SIGINT/SIGTERM | finishes the current batch, commits, exits 130 | re-run the same command |
| second SIGINT, SIGKILL, host/container crash, network loss | open batch rolls back (server-side); `client_connection_check_interval=1s` makes PostgreSQL abort the orphaned statement promptly | re-run; the loader waits up to `--lock-wait` seconds (default 30) for the orphan to release the lock |
| two loaders started | second one is refused (session advisory lock) | — |

### Verify-stage

Checks, all of which must pass before activation is allowed:

* batch set complete and contiguous;
* staged row count and ordinal range;
* the Σfingerprint of staged rows equals the Σ of the checkpoints, and the same holds for units and cents;
* reference domain (tenants, customers, products, category = f(product));
* Σn, Σunits and Σcents of both delta tables equal the staged totals.

### Activate (atomic publication)

A single transaction:

1. `LOCK orders, daily_product, hourly_category IN EXCLUSIVE MODE`. This blocks writers but **not readers**:
   API reads use `ACCESS SHARE` and keep seeing the pre-activation snapshot.
2. Provenance check: the number of existing bulk rows must equal `prefix_rows`. With
   `--prefix-check fingerprint` (the default), the prefix's fingerprint is also recomputed and compared.
3. Insert the tenant/product/customer reference rows (`ON CONFLICT DO NOTHING`).
4. `ALTER TABLE orders DISABLE TRIGGER rollups`. This is transactional, never visible to another session, and
   undone on rollback. Then `INSERT … SELECT … FROM loader.stage_orders ORDER BY tenant_id, ordered_at`, with
   FK checks and all indexes still active. Then the trigger is re-enabled.
5. Rollups `+=` staged deltas (`INSERT … ON CONFLICT DO UPDATE SET n=n+excluded.n …`).
6. `TRUNCATE` the staging tables (frees disk at commit) and mark the run `active`. **COMMIT.**

Why the additive merge is exact: both rollups are signed sums of the trigger's per-row deltas, so
`rollup(old ∪ new) = rollup(old) + rollup(new)`. That holds even when API INSERT/UPDATE/DELETE ran on `orders`
between staging and activation (tested). No full-source GROUP BY is needed. Any single-statement API query
sees either the old or the new (source, rollup) pair, never a mix (tested with a concurrent reader).
`backend/analytics.py` issues each analytic as one statement.

`--mode rebuild-index` drops and recreates the secondary indexes inside the transaction under
`ACCESS EXCLUSIVE`, which blocks readers. At 1M it gave no speed-up, so the default stays `incremental`
(see the test report).

A failed activation rolls back completely. The run stays `verified` with its stage intact, so re-running
retries only the activation.

### Shadow rebuild (evaluated, implemented as a repair tool)

`rebuild-rollups` builds `<rollup>__shadow` from the source with writes paused (`EXCLUSIVE` on `orders`).
It recreates RLS, policies, grants and the PK, reports drift, then swaps by `DROP` + `RENAME` in the same
transaction. Readers keep using the old, consistent rollups until the commit. Existing pooled sessions'
cached trigger plans re-resolve to the new tables (tested).

It is **not** used in the load path, because additive merge is exact and its cost is proportional to the rows
added. A shadow rebuild without pausing writes would need change capture, which means a shared trigger/schema
change. That was not done: it needs agreement first.

### Safety gates

* More than 1,000,000 rows needs `--allow-full-scale` **and** `AGRREGATEX_LOADER_ALLOW_FULL_SCALE=1`
  (integration gate).
* Above 1M rows the loader also requires 30 GiB free at `--disk-path` (overridable with `--min-free-gib`).
* The loader never deletes activated data. `abort` only discards an unactivated stage.
* Bookkeeping lives in schema `loader`, which the API role cannot access. No change to the frozen public
  schema, API or rollup semantics.

## Commands

Connection: `--dsn`, else `$ADMIN_DATABASE_URL`, else `$LOADER_DSN`, else the repository `.env`
(`agrregatex_owner@127.0.0.1:25432/agrregatex`). The DSN is never printed. Requires `psycopg[binary]==3.2.3`
(already pinned in `pyproject.toml`) on the host running the loader.

```bash
# full pipeline; re-run the identical command to resume after any interruption
python3 generator/loader.py load --rows 1000000 --tenants 10 [--batch-size 50000] [--verify-rollups]

# step by step
python3 generator/loader.py init                     # apply loader migrations (idempotent)
python3 generator/loader.py plan --rows R --tenants T [--prefix-rows P --prefix-tenants PT]
python3 generator/loader.py stage [--max-batches K]  # resumable; Ctrl-C stops at a batch boundary
python3 generator/loader.py status [--exact]         # progress, rows/s, ETA, next step (JSON)
python3 generator/loader.py verify-stage
python3 generator/loader.py activate [--mode incremental|rebuild-index] [--lock-timeout 10s]
python3 generator/loader.py finalize                 # VACUUM ANALYZE
python3 generator/loader.py verify-rollups [--tenant N]   # read-only full reconciliation; exit 1 on mismatch
python3 generator/loader.py rebuild-rollups          # repair: shadow build + atomic swap (pauses writes)
python3 generator/loader.py manifest                 # dataset manifest JSON (also generator/results/)
python3 generator/loader.py abort                    # discard an unactivated run

# Phase 00 compatible entry point (used by scripts/verify.sh)
python3 generator/load.py 1000000 10
python3 generator/load.py 10000000 100   # gated; extends an existing 1M baseline as prefix
```

Exit codes: 0 ok, 1 verify-rollups mismatch, 2 refused (precondition, gate, lock), 3 conflict (data
disagrees with the spec; nothing changed), 130 stopped at a batch boundary.

### 10M command (only after the integration gate)

Fresh volume (recommended for matched G-5 comparisons):

```bash
AGRREGATEX_LOADER_ALLOW_FULL_SCALE=1 python3 generator/loader.py load --rows 10000000 --tenants 100 --allow-full-scale
```

Extending the Phase 00 1M baseline in place:

```bash
AGRREGATEX_LOADER_ALLOW_FULL_SCALE=1 python3 generator/loader.py load --rows 10000000 --tenants 100 \
  --prefix-rows 1000000 --prefix-tenants 10 --allow-full-scale
```

**Tenant-domain caveat:** in prefix mode, the first 1M rows use the 10-tenant mapping. Expected at 10M:
tenant 1 ≈ 4.0M, tenant 2 ≈ 2.0M, tenants 3–10 ≈ 87k each, tenants 11–100 ≈ 37k each. A fresh load gives
≈ 41k for every tenant from 3 to 100. Pick deliberately, and record `manifest.prefix`.

## Manifest interface (for the benchmark harness)

`SELECT manifest FROM loader.dataset_manifest` returns zero rows or one `jsonb` value (`manifest_version: 1`;
fields may be added but are never renamed or removed). The same document is printed by
`loader.py manifest`, which works through `scripts/db.py query_json` as the owner role.

| Field | Meaning |
|---|---|
| `manifest_version`, `official_dataset_compatibility` (`"NOT VERIFIED"`) | contract / honesty marker |
| `run_id`, `state`, `generator`, `generator_version`, `seed`, `batch_size`, `loader_commit` | dataset identity and provenance |
| `target_rows`, `spec_tenants`, `prefix{rows,tenants,check}` | declared spec |
| `load_completed_at` | activation commit timestamp |
| `source_rows`, `bulk_rows`, `api_rows`, `tenant_count`, `tenant_distribution[{tenant_id,rows,bulk_rows}]` | live counts, computed at query time (full scan) |
| `stage_verification{passed,checks}`, `activation{mode,inserted,transaction_seconds,wal_bytes}` | load evidence |
| `validations{verify-rollups|rebuild-rollups:{passed,validated_at,after_load,source_orders,mismatches}}` | latest post-load validation results |

## Known limitations

* Activation is one transaction by design (atomic visibility). At 10M, writes are blocked for its whole
  duration (estimated minutes) and API writes fail at their 3 s timeout. Reads continue. This is a
  maintenance window. Splitting activation into chunks would expose partial datasets.
* Activation WAL is roughly 450 B/row, about 4.5 GB at 10M in one transaction, with more than one checkpoint
  expected (`max_wal_size=2GB`).
* FK checks are kept during activation. Skipping them (`session_replication_role=replica`) measured only
  about 19% faster at 1M and would need explicit validation, so it was not adopted.
* Verified only on local PostgreSQL 17.6 (macOS, no container limits), not on the Fedora/Podman
  PostgreSQL 18.6 deployment with its 1.5 CPU / 1.8 GiB limits. All 10M figures are extrapolations.
* The loader runs on the host and needs psycopg there. The Phase 00 `scripts/db.py run_python` path
  (single file piped into the API container) cannot read the migration files.
* `rebuild-rollups` pauses writes for the full GROUP BY. Online rebuild needs a shared change-capture change.
