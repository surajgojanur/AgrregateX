# AgrregateX benchmark and acceptance report

**Run date:** 2026-10-31 UTC
**Command:** `python3 benchmarks/acceptance.py --bounded`
**Runner:** COMPLETED
**Overall PRD result:** FAIL for this bounded run; official full-scale compliance is NOT VERIFIED.

This run used the existing representative 1M database. It did not invoke the loader, rebuild the database, restart containers, or modify the original pg_trickle demo. The runner completed all five steps and verified the source and rollup snapshots were unchanged.

## Environment and dataset

- Fedora 44, x86_64, Intel host; PostgreSQL 18.6 in rootless Podman.
- AgrregateX API: `http://127.0.0.1:18081`; PostgreSQL host port 25432.
- Source: 1,000,000 orders across 10 populated tenants; total gross is 62,725,437,185 cents.
- Skew: tenant 1 has 401,067 orders, tenant 2 has 199,325, and tenants 3–10 have 49,313–50,256 each. Largest/smallest ratio is about 8.1x.
- Rollups: 82,256 `daily_product` rows and 331,361 `hourly_category` rows before and after.
- Dataset uses the project representative seed-42 generator. Official generator/schema compatibility is **NOT VERIFIED**.
- The report's machine-readable run artifact is `benchmarks/results/acceptance.json`; raw detailed artifacts are local and git-ignored.

## Functional and security checks

`functional.py` completed **163/163 assertions**, with zero failures. The cases cover source-oracle counts/totals; UTC hourly/daily trends, zero buckets, and partial boundaries; exact Top-N with deterministic ties; category/status breakdown; insert, update, cancellation, historical movement and delete; idempotency/replay and conflict behavior; rollback atomicity; concurrent duplicate creation; API health, dashboard and OpenAPI; and tenant/path/body authorization.

The HTTP oracle ran 65 comparisons while holding a `SHARE` lock on source orders; all matched. Full source-to-rollup reconciliation found zero mismatches in each of the two maintained rollups. Both functional and HTTP fixture cleanup snapshots matched the baseline.

Security checks passed for 100 API identities, including 9,900 cross-identity freshness-path rejection pairs, RLS and pooled-connection context checks. The dataset has only 10 populated tenants: this is evidence for those 10 data-bearing tenants, not a 100-populated-tenant dataset test.

## HTTP latency (G-1, 1M only)

The harness completed **720/720 HTTP requests** with zero errors. It covered summary, daily and hourly trends, exact Top-N and breakdown, for hot/second/small tenant roles, four ranges (day, week, month, partial boundary), eight sequential repetitions and four-client concurrent rounds.

| Family / mode | Requests | p50 ms | p95 ms | p99 ms | Maximum ms |
|---|---:|---:|---:|---:|---:|
| Summary, sequential | 96 | 3.470 | 10.156 | 12.943 | 12.943 |
| Summary, 4 concurrent | 48 | 13.580 | 38.709 | 46.852 | 46.852 |
| Daily trends, sequential | 96 | 3.788 | 11.028 | 17.147 | 17.147 |
| Daily trends, 4 concurrent | 48 | 13.629 | 54.976 | 61.660 | 61.660 |
| Hourly trends, sequential | 96 | 8.804 | 29.619 | 43.735 | 43.735 |
| Hourly trends, 4 concurrent | 48 | 22.519 | 64.019 | 78.787 | 78.787 |
| Top-N, sequential | 96 | 3.608 | 8.521 | 11.462 | 11.462 |
| Top-N, 4 concurrent | 48 | 15.508 | 36.403 | 50.473 | 50.473 |
| Breakdown, sequential | 96 | 4.391 | 10.021 | 16.282 | 16.282 |
| Breakdown, 4 concurrent | 48 | 14.094 | 41.587 | 56.177 | 56.177 |

G-1 passed this measured 1M set: maximum 78.787 ms (<200 ms). This does not establish the 10M target.

## Freshness (G-2, 1M only)

Thirty commit-to-correct-response observations covered 10 inserts, 10 updates, and 10 cancellations. All passed; worst observed visibility time was **0.216 seconds**. Fixture cleanup and source snapshots matched. This is 1M representative-data evidence only.

## Database safety (G-3; measured FAIL)

The latest bounded run used eight randomized matched pairs. Each arm executed 120 mixed OLTP transactions (60 selects, 30 updates, 30 inserts), targeting 40 OLTP operations/second; loaded arms also targeted 20 dashboard requests/second using four workers distributed across four tenants to avoid intentionally triggering the API's per-tenant concurrency guard. The sequence was the same within each pair, and baseline/load arm order was randomized.

Observed achieved rates were 39.14–39.77 OLTP transactions/second and 20.87–21.18 dashboard requests/second. There were zero operational errors and zero dashboard HTTP errors. The artifact contains 1,920 raw operation timings, 32 phase events, and 27 telemetry samples with container CPU, memory and block I/O plus PostgreSQL WAL counters, lock counts/waiters and database activity counters.

| Full transaction latency | Baseline | Dashboard load | Slowdown |
|---|---:|---:|---:|
| Mean | 1.572 ms | 1.664 ms | +5.84% |
| p50 | 1.490 ms | 1.542 ms | — |
| p95 | 2.969 ms | 4.471 ms | +50.59% |
| p99 | 9.766 ms | 8.668 ms | — |
| Maximum | 26.994 ms | 17.595 ms | — |

Across eight matched pairs, the mean of pair-level mean slowdowns was +6.13%; the median pair-level p95 slowdown was +25.13%. The worst pair had +37.01% mean and +86.09% p95 slowdown. Operation-level statistics are retained in the JSON artifact.

**G-3: FAIL.** The pooled and matched-pair p95 slowdowns exceed 10%, despite the pooled mean being +5.84%. The distribution is variable; this run is not evidence of a stable improvement or a backend architecture decision. The harness now preserves the p95/tail result and fails closed. Follow-up should examine repeated safety runs under controlled host background load and record the same telemetry; no architecture change is made here.

## PRD scorecard

FR results describe the bounded representative dataset and tested API contracts, not the complete official-scale problem.

| Requirement | Result | Evidence / limit |
|---|---|---|
| FR-1 counts and totals | PASS (bounded) | Exact tenant/time-range source oracle and deterministic fixtures. |
| FR-2 trends | PASS (bounded) | Exact UTC hourly/daily results, zero buckets and partial-boundary fixtures. |
| FR-3 exact Top-N | PASS (bounded) | Period-aware source oracle and deterministic tie case. |
| FR-4 breakdown | PASS (bounded) | Status/category results matched source queries. |
| FR-5 tenant isolation | PASS (10 populated tenants) | 100 API identities, RLS and cross-tenant tests; not a 100-populated-tenant dataset. |
| FR-6 mutations and replay | PASS (bounded) | Insert/update/cancel/delete, historical changes, duplicate replay, conflict and rollback checks. |
| FR-7 API | PASS (bounded) | Health, REST calls, dashboard and OpenAPI/Swagger checks. |
| G-1 query speed <200 ms | PASS (1M only) | 720/720 HTTP successes; maximum 78.787 ms. |
| G-2 freshness <30 sec | PASS (1M only) | 30/30 observations; maximum 0.216 sec. |
| G-3 DB slowdown <10% | FAIL | Full mixed transaction p95 slowdown +50.59%; matched median pair p95 +25.13%. |
| G-4 exact correctness | PASS (measured 1M scopes) | 65 API/source comparisons and two full rollup reconciliations; zero mismatches. |
| G-5 growth <2x, 1M to 10M | NOT TESTED | No 10M dataset or valid matched 10M artifact was run. |

**Full PRD status: NOT VERIFIED.** G-3 failed; official dataset compatibility and 10M growth are untested. A local representative 1M pass cannot establish full PRD compliance.

## Reproduction and safeguards

Run unit checks with:

```bash
python3 -m unittest discover -s benchmarks/tests -v
python3 -m py_compile benchmarks/*.py benchmarks/tests/*.py
```

Run the bounded live acceptance suite with:

```bash
python3 benchmarks/acceptance.py --bounded
```

It requires the existing 1M/10-tenant database, does not invoke any loader, scopes fixtures to unique API idempotency keys and reserved empty date ranges, and checks before/after source and rollup snapshots. The 10M growth scorer remains a scoring-only operation and returns NOT TESTED without verified comparable artifacts.
