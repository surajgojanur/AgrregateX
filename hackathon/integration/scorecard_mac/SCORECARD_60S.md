# 60-second judge scorecard (judge-safe)

> All our measurements use **synthetic** data we generated (1M orders / 10 tenants and 10M / 100 tenants, skewed). It is shaped like the PRD test, but it is **not** the organizer's generator. **Nothing here is an official organizer qualification.**

| Target | What we measured | Honest status |
|---|---|---|
| **G1 speed** (< 1 s / < 200 ms) | At 10M: 3,600 HTTP requests, 0 errors. All 72 scenarios had p95 under 1 s, and 71 were under 200 ms. The slowest was the biggest tenant's 90-day Top-10 at 240 ms | Good everywhere, Great almost everywhere. Not yet at a 200-sample protocol |
| **G2 freshness** (< 5 min / < 30 s) | At 1M with 5 writes/s: 8 probes, median 17 s, worst 24 s. At 200 writes/s, 18 of 20 probes exceeded 30 s | Great at low write rates only. Sustainable rate not proven |
| **G3 DB safety** (< 25 % / < 10 %) | The laptop A/B test was disturbed by host freezes | **Not qualified.** Needs a proper host |
| **G4 correctness** (most / all match) | Exact before writes (0 mismatches, 1M and 10M). **After insert-then-update writes, the product summary drifted.** We traced it to one rule in pg_trickle's change reducer, proved the fix in a truth table, and coded it (draft PR #58) | **FAIL until the patched engine passes the regression run** |
| **G5 growth** (< 5× / < 2×) | 10M vs 1M median 1.18×; 71 of 72 under 5×; worst 5.18× | Good on 71/72. Mid and small tenants did not grow, so the ratio is optimistic for them |

**Isolation and resilience (FR5):** a cross-tenant read returns 403. The database enforces tenant filtering with forced row-level security. When a shard is cut off, its tenants fail closed with 503 in about 3 s, the other shard is unaffected, and service recovers 3 s after restore.

**Bonuses:** B-1, B-2 and B-3 are verified live. B-4 is built, with its live proof pending. B-5's monitoring page is shown with its known "degraded" health state.
