# Codex handoff — Phase 01B

**Status:** DONE — WAITING FOR REVIEW. Do not merge or start Phase 02 from this handoff.

## Branch and delivery

- Branch: `test/prd-benchmark-suite`
- PR: https://github.com/surajgojanur/AgrregateX/pull/2 (open, review requested through Issue #1)
- Issue #1: https://github.com/surajgojanur/AgrregateX/issues/1

## Evidence

- `python3 -m py_compile benchmarks/acceptance.py benchmarks/growth.py benchmarks/run.py` passed.
- `python3 benchmarks/acceptance.py --bounded` completed in 92.6 seconds and verified baseline cleanup.
- Functional fixtures: 150 passed, 0 failed.
- HTTP: 720/720 successful; maximum 63.16 ms; five query families with sequential and four-client concurrency coverage.
- Source correctness: 65 comparisons under a source-write-blocking SHARE lock; zero mismatches. Both full rollup reconciliation checks returned zero mismatches.
- Freshness: 30 samples; worst 0.423 seconds.
- Tenant isolation: 100 API identities passed; dataset has real rows for only 10 tenants.
- G-3 failed; transaction mean slowdown 42.71%, p95 16.75%. Earlier run also exceeded p95 limit; repeat under controlled conditions before architecture decisions.
- G-5 NOT TESTED; the suite did not run the loader or create 10M rows.

## Files

- `benchmarks/acceptance.py`: safe bounded orchestrator and machine-readable grader.
- `benchmarks/run.py`: HTTP distributions, request failures, exact source oracle and full rollup reconciliation.
- `benchmarks/growth.py`: verifies scale metadata and refuses to infer G-5 without real 1M/10M artifacts.
- `docs/BENCHMARK_PLAN.md`
- `docs/BENCHMARK_TEST_REPORT.md`
- `docs/collaboration/codex/STATUS.md`

Raw machine-specific artifacts are ignored under `benchmarks/results/`; the report records the primary measurements. The database baseline remained 1,000,000 orders, 10 tenants, and unchanged rollup counts.
