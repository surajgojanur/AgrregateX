# Optimization decisions (issue #67)

Changes are ranked by expected gain against their risk to G2, G3 and G4. Nothing here is applied; each item needs its own approval. TEST means it is worth an approved experiment, DEFER means wait for a dependency, and REJECT means not worth doing.

| # | Change | Targets | Gain | Risk | Decision |
|---|---|---|---|---|---|
| 1 | **PR #58 net-change reducer fix** (keep earliest D only if the history starts with D, latest I only if it ends with I; keyed sources only) | G4, FR1/3/4/6 | Removes the ghost and double-count class (truth table 12/12) | Engine patch; needs the runtime matrix (TEST_PLAN §A) | **TEST first** (P1). It is the release blocker |
| 2 | Interim mitigation: FULL refresh for `st_day_product_status` only | G4 | Correct by construction | 149.8 s per refresh at 10M breaks G2 Great/Good at scale and adds G3 load | **DEFER** to demo-scale only, with approval (the operator approved it for demo configs under #29; not applied yet) |
| 3 | Raw-source read mode (`AX_ANALYTICS_READ_MODE=raw_source`) as the correctness fallback | G4 | Correct from source | G1 at 10M is unmeasured (largest tenant 90 d scans about 1.9M rows), and G3 load is higher | **TEST** on a disposable 1M/10M stack (#55) before any demo use |
| 4 | Index `(tenant_id, utc_day, status, product_id) INCLUDE (sales_cents, units, order_count)` on `st_day_product_status` for the worst Top-N | G1, G5 worst case (240.56 ms) | Likely an index-only scan for the stream-table part | Write amplification on every refresh (G2/G3) | **TEST** with EXPLAIN in P4, adopting it only if refresh time doesn't regress |
| 5 | Product-by-*month* rollup for ranges ≥ 30 d | G1, G5 | Fewer rows for 90 d Top-N | A 4th stream table: more CDC and refresh cost, plus more G4 surface | **DEFER** until after the G4 fix |
| 6 | Batching and schedule (1 s → 2–5 s) under high write rates | G2 sustainability, G3 | Fewer refreshes and less FULL fallback (107 seen at 200 TPS) | A higher floor for freshness | **TEST** in P3 with a step-up rate |
| 7 | Raise `differential_max_change_ratio` / avoid the FULL fallback | G2 at 200 TPS | Fewer 30 s+ timeouts | DIFFERENTIAL on large deltas can be slower | **TEST** in P3 |
| 8 | Response cache in the API | G1 | Faster repeat reads | Cross-tenant cache-leak risk (FR5) and stale numbers (G2) | **REJECT** |
| 9 | Standard `MATERIALIZED VIEW` + periodic `REFRESH CONCURRENTLY` as a **baseline** | Fair comparison | Shows what pg_trickle buys | Baseline only, not a product change | **TEST** as a separate baseline on a resourced host (G2/G3 comparison) |
| 10 | Raw SQL on `ax.orders` with no summaries as a **baseline** | Fair comparison | Same | Same | **TEST** together with #3 |
