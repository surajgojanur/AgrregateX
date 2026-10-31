# OPUS handoff — ENGINE_CONTRACT v1 (P0/P1 engine spike)

**Status:** `HANDOFF_READY` for **interface wiring only**. The performance gates are **NOT met** (see §Findings F3–F5), and the primary
architecture is blocked on [PROPOSAL P1](../proposals/opus/P1-upstream-null-safe-group-join.md), which needs a human decision.
**Branch:** `research/opus-p1-engine-spike` · **Date:** 2026-10-31 · **Data:** REPRESENTATIVE, never organizer data.
Official generator compatibility is **NOT VERIFIED**.

## 0. Environment (exact)

| item | value |
|---|---|
| Engine image | `ghcr.io/trickle-labs/pg_trickle@sha256:94344bb98995b19c826f939739672481abaab8c25710e3910b48bdb7cf5b3b8d` (arm64) |
| PostgreSQL | 18.6 (Debian 18.6-1.pgdg12+2) |
| pg_trickle runtime | **0.108.3**. The repo source is 0.108.4 (patch mismatch, untested). |
| Host | Apple M1, 8 GB, Docker 4 GB / 8 vCPU. Container: `mem_limit 2g`, PGDATA on 1.5 GB tmpfs. |
| Live GUCs (`SHOW`) | `cdc_mode=auto` (image default; we request `trigger` per stream table), `wal_level=logical`, `min_schedule_seconds=1`, `scheduler_interval_ms=500`, `differential_max_change_ratio=0.15`, `max_dynamic_refresh_workers=4`, `per_database_worker_quota=0`, `max_worker_processes=32` |

Every number below comes from n=1 runs on a laptop. They are **indicative, not PRD scoring evidence**; Codex's harness owns G-1..G-5.

## 1. ENGINE_CONTRACT v1 (interface)

Install order (one database): `00_schema.sql` → `05_bucket_columns.sql` → `20_security.sql` (source part) → `10_stream_tables.sql`
→ `20_security.sql` again (stream-table part) → `30_oracle.sql`. If RLS is enabled on a source **after** the stream tables exist, the
stream tables go `SUSPENDED` (F7). Recover with `pgtrickle.reinitialize_stream_table(name)`.

### Source (`ax` schema, representative; map the organizer schema onto it with a view or rename)
`ax.orders(tenant_id int, order_id bigint, customer_id int, product_id int, status text, quantity int, unit_price_cents bigint,
created_at timestamptz, updated_at timestamptz, utc_day timestamp, utc_hour timestamp, line_cents bigint)`, PK `(tenant_id, order_id)`.
- `utc_day`, `utc_hour` and `line_cents` are **trigger-maintained** (`ax.orders_derive_buckets`, a BEFORE ROW trigger), NOT NULL, and
  authoritative: client values are overwritten. Reason: F2.
- `status ∈ {pending, paid, shipped, cancelled, refunded}`.
- `ax.products(tenant_id, product_id, category_id, name)`. Category changes propagate through the join.

### Stream tables (all scheduled `DIFFERENTIAL`, `schedule => '1s'`, `cdc_mode => 'trigger'`)
| name | grain / key (all NOT NULL in source) | measures |
|---|---|---|
| `ax.st_day_product_status` | `tenant_id, utc_day, product_id, status` | `order_count bigint, units bigint, sales_cents numeric` |
| `ax.st_day_category_status` | `tenant_id, utc_day, category_id, status` | same |
| `ax.st_hour_category_status` | `tenant_id, utc_hour, category_id, status` | same |

- **Currency:** integer cents. `sales_cents` is `numeric` (SUM of bigint) and exact; serialize it as a string or integer, never a float.
- **Time:** `utc_day`/`utc_hour` are `timestamp` values in UTC. The API converts request bounds to UTC, then uses half-open ranges `[from, to)`.
- **Sales semantics (PROPOSED, confirm with organizer):** revenue = `status NOT IN ('cancelled','refunded')`. Every status row is
  kept, so the API can choose.
- **Top-N:** sum `sales_cents` over the requested days per `product_id`, then `ORDER BY sales DESC, product_id ASC LIMIT n`
  (deterministic ties). Never sum per-day Top-N lists.
- **Exact arbitrary windows:** full UTC days come from the `st_day_*` tables. A partial first or last day for products comes from
  raw `ax.orders` over `[from, next_day)` and `[last_day, to)`, using `orders_tenant_created_idx`. For category breakdowns at hourly
  precision, use `st_hour_category_status` for full hours and raw edges below one hour.
- **Indexes:** pg_trickle `auto_index` creates `(tenant_id, utc_<grain>, <dim>, status)`, which serves tenant+range scans. Do not add more (each one adds refresh cost).
- Never read the hidden columns `__pgt_*`, and never read `pgtrickle_changes.*`.

### Security contract (shared-DB topology)
- The API connects as **`ax_api`** (LOGIN, NOBYPASSRLS, not an owner). The password is set out of band and never committed.
- Per request: `BEGIN; SELECT set_config('ax.tenant_id', '<verified tenant>', true); …; COMMIT;`. The setting is transaction-local. With a pooler, always use the `true` (local) form.
- RLS is `ENABLE` + `FORCE` with policy `tenant_id = ax.current_tenant()` on all three stream tables **and** on `orders` and `products` (needed for raw edges).
- Stream-table owner = superuser. pg_trickle only keeps a source with RLS on DIFFERENTIAL for a superuser or BYPASSRLS owner (verified: F7).

### Freshness contract (for B-1)
- **Do NOT use `pgt_status().staleness` / `data_timestamp` as "freshness".** They do not advance on NO_DATA refreshes, so an idle,
  fully current table looks stale (F6).
- Use instead, per stream table: the last `pgtrickle.pgt_refresh_history` row with `status='COMPLETED'` (any action),
  `end_time` as the "verified as of" time, and its `action`. Report commit→visible lag only from an actual probe (`lag_probe.py`).

### Validation commands
```bash
docker compose -f hackathon/integration/spike-compose.yaml up -d --wait      # port 127.0.0.1:25540, tmpfs
# see hackathon/integration/README.md for the full reproduce script
psql ... -c "select * from ax.oracle_mismatches()"          # every row (0,0) == exact
psql ... -c "select * from ax.refresh_audit(now()-interval '10 min')"   # any FULL / fallback=t on a DIFFERENTIAL table == FAIL
```

## 2. Findings (observed vs hypothesis)

| # | Finding | Evidence |
|---|---|---|
| F1 | **Correctness held in every completed run.** The oracle (EXCEPT ALL both ways) was 0/0 for DIFFERENTIAL, IMMEDIATE, after FULL fallbacks, after reinitialize, and with source RLS. Mutations covered insert, cancel, refund, quantity change, price change, bucket moves across hours/days, product (category) moves, deletes, and product recategorization. | `results/ab-*.txt`, `results/rls-source-reinit.txt` |
| F2 | **GROUP BY shape decides the refresh strategy.** (a) `GROUP BY date_trunc(...)` directly: FULL fallback, `DISTINCT_AGG_BOUNDED_STATE_FULL_FALLBACK … not a simple column`. (b) The same expression inside a subquery: DIFFERENTIAL, but slow (F3). (c) `GENERATED … STORED` columns: the **CDC buffer doesn't capture them** and the stream tables went to permanent ERROR (`column c.utc_day does not exist`). (d) Trigger-maintained plain columns work. | handoff session logs, `sql/05_bucket_columns.sql` header |
| F3 | **Upstream performance bug (blocking).** The aggregate delta joins existing stream-table rows on `IS NOT DISTINCT FROM`, which can only run as a nested loop. Refresh ≈ 5 ms per changed group at an 88k-row stream table: 10 changes → 0.1s, 100 → 0.65s, 1,000 → 5s, 8.7k → 31s. The same join with `=` took 25 ms versus 23,076 ms. | PROPOSAL P1 |
| F4 | **G-3 indicative FAIL for scheduled DIFFERENTIAL:** pgbench (4 clients, 20s, 1 read + 1 update + 1 insert per transaction) went from 2,458 tps / 1.63 ms with no stream tables to **1,761 tps / 2.27 ms (−28%)**. During that run 0 refreshes completed, staleness reached 22s, and the change buffer held 22 MB. | `results/oltp-A.txt`, `oltp-B.txt` |
| F5 | **IMMEDIATE rejected:** 0.11 tps, 35.9 s average transaction latency (3 stream tables maintained synchronously, each paying F3). The results were exact. | `results/oltp-C.txt` |
| F6 | **Idle lag is fine:** DIFFERENTIAL 1s, 15 samples, 0 timeouts. Insert p50 0.94s, max 1.78s; cancel p50 1.52s, max 2.23s. Under sustained load this degrades (F4). `data_timestamp` doesn't advance on NO_DATA. A server-side polling loop holds back the frontier ("frontier holdback active"), so probes must poll client-side in autocommit. | `results/lag-diff-1s-idle.json` |
| F7 | **RLS:** all five isolation tests pass (no tenant → 0 rows; cross-tenant → 0; transaction-local; injection-like value → error; no access to buffers or writes). Enabling RLS on sources after creation **SUSPENDS** the stream tables; `reinitialize_stream_table` recovers them, and the steady state is DIFFERENTIAL with no fallback. | `results/rls-test.txt`, `results/rls-source-reinit.txt` |
| F8 | **Reliability:** after repeated drop/recreate cycles in one DB, the scheduler stopped scheduling 2 of 3 stream tables (no history rows, `health_check` = stale) while manual refresh worked. Toggling `pg_trickle.enabled` didn't help. Terminating the scheduler backend did: the launcher respawned it in about 30–45s, and refreshes and the oracle recovered. Root cause not established. Mitigation: avoid drop/recreate in the demo, alert on `health_check()` `stale_tables`, and treat restart-scheduler as the B-2 runbook step. | session log |
| F9 | **Burst fallbacks:** more than 15% of a source changed per refresh triggers FULL (`DELTA_RATIO_EXCEEDED`). Products is small (2,000 rows), so recategorizing 301 products forced FULL. Refresh also drains bursts in bounded batches (about 1.4–2.3k delta rows per refresh). | `results/ab-*` (session 1) |
| F10 | **Reads at 100k don't need stream tables yet:** 30-day Top-10 for the heaviest tenant took 22 ms raw versus 20 ms from the stream table; 90 days took 42 versus 20 ms. Stream-table rows per tenant are bounded by days × products × statuses, while raw rows grow with volume. **Hypothesis:** the gap widens at 10M (to be measured on Fedora). | `results/read-raw-vs-st.txt` |
| F11 | **Multi-DB:** one instance ran 2 databases with independent schedulers (1 launcher + 1 scheduler per database), each with its own DIFFERENTIAL stream tables. pg_trickle can't join across DBs. **100-DB budget:** `max_worker_processes ≥ 1 launcher + 100 schedulers + max_dynamic_refresh_workers + autovacuum_max_workers + max_parallel_workers` ≈ 116+ (the current 32 is insufficient). Set `per_database_worker_quota`. Not feasible on an 8 GB laptop without measurement, so ask the organizer for the topology first. | `results/two-db-evidence.txt` |

## 3. Recommendation

1. **Primary:** Strategy A (scheduled DIFFERENTIAL + tenant-keyed stream tables + RLS), **conditional on PROPOSAL P1** (upstream
   patch to the hashable delta join). Without P1, A fails G-2 and G-3 under any sustained write load.
2. **Rejected:** B (IMMEDIATE), 0.11 tps.
3. **Fallback if P1 is REJECTED or fails its A/B:** C (logical replication to a separate analytics PG running A) for G-3, accepting
   G-2 risk under load; or D (hand-maintained keyed rollups, previously −26%).
4. **Not affected by the decision:** Codex can wire the API now against the §1 names, columns and security contract. Those don't
   change under A + P1 or C.

## 4. Unverified / open
- Organizer schema, generator and topology (single DB with `tenant_id`, or one DB per tenant).
- 0.108.4 behaviour (only 0.108.3 tested); WAL CDC (`cdc_mode=wal`) A/B; 1M / 10M scale; 5s/10s schedules under load.
- B-2 restart/crash replay drill; the scheduler stall (F8) root cause.
- Matched, randomized repeated G-3 runs (Codex harness). Everything here is n=1.
