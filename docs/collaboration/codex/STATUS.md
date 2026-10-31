# Codex status — Phase 01B review fixes

**Status:** DONE — WAITING FOR REVIEW
**Branch:** `test/prd-benchmark-suite`
**Ownership:** `benchmarks/**`, benchmark-specific docs, and `docs/collaboration/codex/**`.
**PR:** [#2](https://github.com/surajgojanur/AgrregateX/pull/2)
**Coordination:** [Issue #1](https://github.com/surajgojanur/AgrregateX/issues/1)

Changes address explicit fail-closed requirement coverage, exact request/correctness matrices, strict 1M/10M growth comparability, current-run/failure artifacts, and paired G-3 measurement with phase and resource telemetry. The bounded run used the preserved 1M / 10-tenant representative dataset only. No loader, backend, shared schema, Compose or original pg_trickle demo changes were made.

Latest bounded results: 163/163 functional assertions passed; 720/720 HTTP requests passed (maximum 78.787 ms); 65 source-oracle comparisons and both full rollup reconciliations had zero mismatches; 30 freshness observations passed (worst 0.216 seconds); 100 API identities and 9,900 cross-identity rejection pairs passed. Source/rollup baseline remained unchanged.

G-3 is **FAIL**: 8 randomized pairs, 960 operations per arm, no HTTP errors, achieved target rates, and telemetry captured. Mixed transaction mean slowdown was +5.84%; pooled p95 slowdown was +50.59%, and median paired p95 slowdown was +25.13%. G-5 is **NOT TESTED**: no 10M dataset was run. Official dataset compatibility remains **NOT VERIFIED**.

See [BENCHMARK_TEST_REPORT.md](../../BENCHMARK_TEST_REPORT.md) for full measurements and limitations.
