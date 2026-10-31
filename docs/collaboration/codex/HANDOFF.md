# Codex handoff — Phase 01B review fixes

**Status:** DONE — WAITING FOR REVIEW. Do not merge or start Phase 02 from this handoff.

## Branch and review

- Branch: `test/prd-benchmark-suite`
- PR: https://github.com/surajgojanur/AgrregateX/pull/2
- Coordination: https://github.com/surajgojanur/AgrregateX/issues/1

## Review fixes

- Explicitly require exact named FR test counts and full HTTP/correctness matrices before scoring PASS; missing, duplicate, or partial evidence becomes NOT TESTED.
- Require exact rollup names and count, zero request/oracle errors, populated-tenant data evidence and stable source snapshots.
- G-5 now refuses incomplete/failed artifacts and requires matched full case keys and observation counts, official compatibility, identical dataset/generator/seed, workload, hardware (including CPU and RAM), and PostgreSQL version.
- Acceptance artifacts are written at start and after scoring; runner execution status is independent from PRD target status.
- G-3 now uses eight randomized matched pairs, varied tenant selection, a mixed read/update/insert workload, separate statement/COMMIT/full transaction timings, actual throughput/error checks, and PostgreSQL plus container CPU/I/O/WAL/lock telemetry. It reports pooled and paired distributions and scores strictly against its declared mixed-workload rule.
- Safety and functional fixtures clean only rows in reserved empty ranges and verify source/rollup snapshots.

## Latest bounded evidence

- Machine: Fedora 44 x86_64, PostgreSQL 18.6 in rootless Podman; existing 1M / 10-tenant representative dataset.
- Functional: 163/163 assertions passed.
- HTTP: 720/720 successful; maximum 78.787 ms.
- Correctness: 65 API/source comparisons and two full rollup comparisons; zero mismatches.
- Freshness: 30/30 passed; worst 0.216 seconds.
- Tenant isolation: 100 credential identities and 9,900 cross-identity rejection pairs; dataset has 10 populated tenants.
- G-3: FAIL. Eight pairs / 960 operations per arm; 39.14–39.77 OLTP ops/s, 20.87–21.18 dashboard req/s, zero errors. Mixed transaction mean slowdown +5.84%; pooled p95 +50.59%; median paired p95 +25.13%. High tail variability is retained as a failure, not normalized away.
- G-5: NOT TESTED; no 10M load or benchmark was run. Official dataset compatibility remains NOT VERIFIED.
- Baseline: unchanged 1,000,000 orders, 10 tenants, 82,256 daily rollup rows, 331,361 hourly rollup rows.

## Verification commands

```bash
python3 -m unittest discover -s benchmarks/tests -v
python3 -m py_compile benchmarks/*.py benchmarks/tests/*.py
python3 benchmarks/acceptance.py --bounded
python3 benchmarks/growth.py
```

Latest run: 10 unit tests passed; Python compilation and `git diff --check` passed. The bounded acceptance runner completed all five stages with stable before/after snapshots. The growth scorer returned NOT TESTED because there is no valid 10M artifact pair.

No loader, API/backend, shared schema, Compose, or upstream demo files were modified. No commit has been merged and no 10M import was started.
