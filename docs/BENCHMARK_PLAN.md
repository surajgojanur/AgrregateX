# AgrregateX PRD acceptance and benchmark plan

This suite measures the frozen API against the official seven functional requirements and five Great targets. It treats the existing seed-42 1M dataset as representative only; the organizer's generator has not been validated. The scripts never create a 10M dataset.

## Commands

With the AgrregateX Compose services running locally on the configured ports:

```bash
python3 benchmarks/acceptance.py --bounded
python3 benchmarks/growth.py
```

The bounded command refuses to run unless the source has exactly 1,000,000 orders. It runs deterministic functional fixtures, 720 HTTP requests, source-oracle comparisons under a source-table SHARE lock, 30 insert/update/cancel freshness observations, the paired OLTP safety experiment, and tenant authorization checks. Fixture-based tests use unique identifiers and clean up their own records. Before/after source count, gross cents and rollup counts must match. It does not restart containers or run the loader.

Artifacts are written under `benchmarks/results/`. Raw outputs are ignored by Git because they can be large and machine-specific. The command writes `acceptance.json` as a machine-readable summary. Existing artifact files are not accepted as evidence for a component unless that component completed successfully and rewrote its artifact during the current invocation.

## Coverage and measurement rules

| Requirement | Method |
|---|---|
| FR-1 | Exact source/API oracle for tenant counts and non-cancelled integer-cent totals; fixture tests include empty and partial ranges. |
| FR-2 | Hour/day trend oracle, UTC bucket behavior, zero buckets and partial boundaries. |
| FR-3 | Exact source `GROUP BY` Top-N, including sales/units/product-ID deterministic tie order and selected date range. |
| FR-4 | Exact status/category counts and cancelled-sales semantics. |
| FR-5 | 100 API credentials, cross-tenant path rejection, RLS checks, non-bypass API role, pooled-context reset, concurrent requests and foreign mutation rejection. Only tenants 1–10 have source rows in this dataset. |
| FR-6 | Insert, update, cancellation, historical time/product/category move, delete, duplicate event and concurrent duplicate fixture checks; freshness has repeated insert/update/cancel observations. |
| FR-7 | Health, live API calls and OpenAPI title/document availability. |
| G-1 | Full local HTTP request latency, reporting p50/p95/p99/max and failures by query family. A bounded pass is labeled 1M only. |
| G-2 | Source transaction commit timestamp to observed correct API result for 30 insert/update/cancel observations; report worst elapsed time. |
| G-3 | Three paired baseline/dashboard-load arms, 720 ordinary reads/writes per arm. Compare mean and p95 for read statement, write statement and full transaction; any metric at or above 10% fails. |
| G-4 | Compare API values with direct PostgreSQL source queries while a `SHARE` lock blocks source writes; compare complete maintained rollup tables against grouped source rows. |
| G-5 | `growth.py` accepts only matched 1M/10-tenant and 10M/100-tenant artifacts, filters failed requests and compares matched query, tenant role, range and concurrency cases. Without both verified scale artifacts it reports NOT TESTED. |

## Growth run prerequisites

After the loader owner publishes a stable and safe 10M dataset, run the same HTTP harness with `python3 benchmarks/run.py 10000000`; it verifies and records actual order and tenant counts. A 1M result is collected with `python3 benchmarks/run.py 1000000`. Then run `python3 benchmarks/growth.py`. The 10M artifact must describe 10,000,000 source rows and 100 tenants. The suite does not prescribe or invoke the loader.

## Interpretation

Latency summaries are descriptive observations on the local machine, not guarantees for another host. Dashboard-query target success at 1M does not establish 10M performance. A negative estimated slowdown is retained as measured and is not treated as a speedup claim. The OLTP test must be repeated under representative write rates before making an architectural decision from a noisy result. PASS on functional fixtures or the representative 1M dataset is not a full-scale PRD PASS.
