# AgrregateX benchmark and acceptance report

**Run date:** 2026-10-31 UTC
**Benchmark code commit:** `8d2b3fd3d95f00af60fed39d961587501f8b6b6b`
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
| Summary, sequential | 96 | 3.833 | 8.763 | 9.940 | 9.940 |
| Summary, 4 concurrent | 48 | 8.494 | 17.490 | 23.102 | 23.102 |
| Daily trends, sequential | 96 | 4.175 | 12.466 | 13.498 | 13.498 |
| Daily trends, 4 concurrent | 48 | 9.238 | 23.443 | 32.413 | 32.413 |
| Hourly trends, sequential | 96 | 8.189 | 26.046 | 33.045 | 33.045 |
| Hourly trends, 4 concurrent | 48 | 15.827 | 58.508 | 71.100 | 71.100 |
| Top-N, sequential | 96 | 3.444 | 8.441 | 9.456 | 9.456 |
| Top-N, 4 concurrent | 48 | 11.940 | 28.768 | 43.040 | 43.040 |
| Breakdown, sequential | 96 | 3.825 | 10.456 | 11.758 | 11.758 |
| Breakdown, 4 concurrent | 48 | 8.404 | 18.414 | 21.197 | 21.197 |

G-1 passed this measured 1M set: maximum 71.100 ms (<200 ms). This does not establish the 10M target.

## Freshness (G-2, 1M only)

Thirty commit-to-correct-response observations covered 10 inserts, 10 updates, and 10 cancellations. All passed; worst observed visibility time was **0.184 seconds**. Fixture cleanup and source snapshots matched. This is 1M representative-data evidence only.

## Database safety (G-3; measured FAIL)

The latest bounded run used eight randomized matched pairs. Each arm executed 120 mixed OLTP transactions (60 selects, 30 updates, 30 inserts), targeting 40 OLTP operations/second; loaded arms also targeted 20 dashboard requests/second using four workers distributed across four tenants to avoid intentionally triggering the API's per-tenant concurrency guard. The sequence was the same within each pair, and baseline/load arm order was randomized.

Observed achieved rates were 39.09–39.77 OLTP transactions/second and 20.85–21.16 dashboard requests/second. There were zero operational errors and zero dashboard HTTP errors. The artifact contains 1,920 raw operation timings, 32 phase events, and 27 telemetry samples with container CPU, memory and block I/O plus PostgreSQL WAL counters, lock counts/waiters and database activity counters.

| Full transaction latency | Baseline | Dashboard load | Slowdown |
|---|---:|---:|---:|
| Mean | 2.025 ms | 2.548 ms | +25.82% |
| p50 | 1.589 ms | 1.665 ms | — |
| p95 | 7.312 ms | 9.719 ms | +32.92% |
| p99 | 11.924 ms | 17.060 ms | — |
| Maximum | 19.195 ms | 44.747 ms | — |

Across eight matched pairs, the mean of pair-level mean slowdowns was +33.89%; the median pair-level mean slowdown was +20.78%, and the median pair-level p95 slowdown was +31.30%. The worst pair had +156.67% mean and +435.59% p95 slowdown. Operation-level statistics are retained in the JSON artifact.

A previous bounded run of the same paired harness on the same baseline measured +5.84% pooled mean and +50.59% pooled p95 slowdown (with +6.13% mean of pair-level means). The variation between these completed runs is material. Both runs fail the p95 criterion; neither supports claiming a repeatable improvement.

**G-3: FAIL.** Both pooled mean (+25.82%) and p95 (+32.92%) exceed 10%; matched-pair mean and p95 results also exceed the target. This is consistent with the previous bounded run's elevated p95, while pair-level results show substantial variation. The harness preserves the full distribution and fails closed. Follow-up should examine the dashboard-induced database work and repeat under controlled host background load; no architecture change is made here.

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
| G-1 query speed <200 ms | PASS (1M only) | 720/720 HTTP successes; maximum 71.100 ms. |
| G-2 freshness <30 sec | PASS (1M only) | 30/30 observations; maximum 0.184 sec. |
| G-3 DB slowdown <10% | FAIL | Full mixed transaction mean slowdown +25.82%, p95 +32.92%; matched median pair mean +20.78%, p95 +31.30%. |
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
