# AgrregateX benchmark and acceptance report

**Run:** 2026-10-31 (UTC)
**Harness:** `python3 benchmarks/acceptance.py --bounded`
**Overall:** PARTIAL. The representative 1M checks ran; official generator compatibility and 10M behavior remain unverified.

## Environment and preserved data

- Fedora 44, x86_64, Intel host; PostgreSQL 18.6 in rootless Podman.
- AgrregateX API: `http://127.0.0.1:18081`; PostgreSQL host port 25432.
- Existing dataset: 1,000,000 orders and 10 tenants. It is unevenly distributed: tenant 1 has 401,067 orders; tenant 2 has 199,325; remaining tenants have 49,313–50,256 each. The largest tenant is about 8.1 times the smallest.
- Before and after snapshots both recorded 1,000,000 orders, 10 tenants, 62,725,437,185 gross cents, 82,256 `daily_product` rows and 331,361 `hourly_category` rows. Fixture cleanup was verified.
- Current measured database sizes: orders heap 97 MB, order indexes 602 MB, daily product rollup 7 MB, hourly category rollup 27 MB. These are PostgreSQL relation sizes, not total volume sizes.
- At inspection: PostgreSQL container 181.6 MB, API 41.6 MB; host reported 7.5 GiB RAM and 2.4 GiB available. Container usage is a point-in-time observation, not benchmark peak memory.
- Dataset generator is the project's representative seed-42 generator. **Official dataset compatibility: NOT VERIFIED.**

## Functional checks

`functional.py` executed 150 assertions; 150 passed and 0 failed. It tests exact counts/totals, UTC hourly/daily trend boundaries and zero buckets, deterministic Top-N, category/status breakdowns, create/update/cancel/delete, historical movement, duplicate event replay, conflicting idempotency keys, concurrent duplicate create, rollback behavior, tenant/path/body isolation, monitoring authorization and OpenAPI metadata.

The security matrix passed for 100 API identities with four concurrent workers. It rejected 9,900 cross-tenant freshness-path combinations, checked adjacent cross-tenant query/mutation paths, verified API-role RLS/bypass properties and checked pooled connection context reset. The dataset itself contains records for only 10 tenants, so 100 populated-tenant isolation is not demonstrated.

## HTTP latency and query correctness

The harness issued 720 HTTP requests across summary, daily/hourly trends, Top-N and breakdown. It covered hot tenant 1, tenant 2 and small tenant 10; day, week, month and partial-timestamp ranges; sequential traffic and four concurrent clients. All 720 returned HTTP 200.

| Family / mode | p50 ms | p95 ms | p99 ms | max ms |
|---|---:|---:|---:|---:|
| Summary, sequential | 3.28 | 8.22 | 8.64 | 8.64 |
| Summary, 4 concurrent | 8.03 | 19.16 | 24.64 | 24.64 |
| Daily trends, sequential | 3.69 | 11.04 | 12.33 | 12.33 |
| Daily trends, 4 concurrent | 9.57 | 22.83 | 32.05 | 32.05 |
| Hourly trends, sequential | 8.15 | 27.42 | 32.96 | 32.96 |
| Hourly trends, 4 concurrent | 16.47 | 46.75 | 63.16 | 63.16 |
| Top-N, sequential | 3.26 | 9.63 | 14.83 | 14.83 |
| Top-N, 4 concurrent | 8.69 | 23.80 | 35.28 | 35.28 |
| Breakdown, sequential | 3.58 | 8.96 | 9.51 | 9.51 |
| Breakdown, 4 concurrent | 9.60 | 25.38 | 31.39 | 31.39 |

The maximum successful request was 63.16 ms, so the measured 1M request set was under 200 ms. This does not prove the 10M target.

There were 65 exact API-versus-source comparisons under a `SHARE` table lock that held source writes stable during comparison. There were zero mismatches. A full two-way `EXCEPT ALL` comparison also found zero mismatches for both maintained rollups. These checks cover the tested tenants, ranges and query families, not every conceivable parameter combination.

## Freshness

30 observations covered five insert/update/cancellation sequences. Commit-to-correct-response elapsed time had a worst observation of **0.423 seconds**; all were below 30 seconds. This is 1M evidence only.

## Database safety (G-3 FAIL)

Each of three paired trials used 720 operational transactions per arm, targeting 40 operations/second, while dashboard load targeted 20 HTTP requests/second across four clients. The harness compares both means and p95 values; it fails when any measured slowdown is 10% or greater.

| Metric | Baseline mean ms | Loaded mean ms | Mean slowdown | Baseline p95 ms | Loaded p95 ms | p95 slowdown |
|---|---:|---:|---:|---:|---:|---:|
| Read statement | 0.157 | 0.162 | 3.65% | 0.253 | 0.265 | 4.54% |
| Write statement | 0.364 | 0.379 | 4.32% | 0.537 | 0.569 | 5.97% |
| Full transaction | 2.860 | 4.081 | 42.71% | 9.959 | 11.628 | 16.75% |

**G-3: FAIL in this run.** The transaction metric exceeds the 10% threshold. Do not interpret a separate initial run's negative mean transaction delta as an improvement: its p95 write and transaction slowdowns were 13.70% and 16.00%, respectively. The materially different mean results indicate run-to-run variance; repeat under a controlled background-load and resource-telemetry protocol before using this estimate to select an architecture.

## Great-target status at 1M

| Target | Result | Evidence / limit |
|---|---|---|
| G-1 HTTP query <200 ms | PASS at 1M only | 720 successes, 0 failures, maximum 63.16 ms. |
| G-2 freshness <30 sec | PASS at 1M only | 30 source-commit-to-correct-response observations; worst 0.423 sec. |
| G-3 normal DB slowdown <10% | FAIL | Full transaction mean +42.71%, p95 +16.75% in the recorded run. Initial run also failed on p95. |
| G-4 exact correctness | PASS for measured 1M scopes | 65 API/source comparisons and two full rollup comparisons; zero mismatches. |
| G-5 10M/1M growth <2x | NOT TESTED | No 10M import or benchmark was run. `growth.py` explicitly reports NOT TESTED absent verified artifacts. |

## Functional requirement status

All FR statuses below describe bounded evidence on the representative 1M/10-tenant dataset. They are not a claim that the complete official PRD is satisfied.

| FR | Status | Evidence |
|---|---|---|
| FR-1 | PASS (bounded) | Exact fixture and source-oracle totals, date boundaries, cancelled-sales semantics. |
| FR-2 | PASS (bounded) | UTC hourly/daily trends, partial ranges and zero buckets matched direct SQL. |
| FR-3 | PASS (bounded) | Time-range exact Top-N oracle and deterministic tie order matched. |
| FR-4 | PASS (bounded) | Category/status fixture and direct source oracle matched. |
| FR-5 | PASS (bounded) | 100 API identities; RLS/pooled-context tests; dataset populated for 10 tenants only. |
| FR-6 | PASS (bounded) | Insert, update, cancel, historical movement, delete and duplicate/replay fixtures; freshness measured. |
| FR-7 | PASS (bounded) | Health/API/OpenAPI checks passed. |

## Machine-readable evidence and rerun

`benchmarks/results/acceptance.json` contains the complete current-run summary, query-family distributions, safety metrics, step status and before/after baseline. Detailed request/freshness/safety/functional/security records are in their corresponding ignored JSON artifacts. Re-run with:

```bash
python3 benchmarks/acceptance.py --bounded
python3 benchmarks/growth.py
```

The acceptance run took 92.6 seconds. It did not restart any container, launch the loader, or alter the preserved 1M dataset.
