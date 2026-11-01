# Test plan (issue #67)

Order follows the issue's priority: **G4 → G3/G2 → G1/G5 → FR regression → bonuses.** Each item names the oracle, so a pass is decided by data, not by a refresh timestamp.

## R0: read-only (DONE in this PR)
Recompute G1/G2/G5 from raw artifacts; run every offline suite; run the evidence verifier; reconcile published claims (see `RESULTS.md`).

## A. G4 correctness: regression matrix (patched image, disposable target only)
Run each case **within one refresh window** (scheduler paused, or all statements committed before the next tick) **and across windows**:

| # | Mutation history per order | Expected net effect on the product rollup |
|---|---|---|
| A1 | insert | +1 in (day, product, status) |
| A2 | insert → update status (paid→cancelled) | +1 cancelled only (**#50 case A, ghost today**) |
| A3 | update → delete | −1 old group once (**double-decrement today**) |
| A4 | paid → cancelled → refunded | −1 paid, +1 refunded |
| A5 | delete | −1 |
| A6 | insert → delete | no change |
| A7 | update quantity / price | sales and units move within the group |
| A8 | change product_id (product move) and category move via products | old group −1, new group +1, on the day and category rollups |
| A9 | change created_at across a day/hour boundary | old bucket −1, new bucket +1 |
| A10 | several orders in the same group, mixed histories | sum of the above |
| A11 | ROLLBACK of each history | no change |
| A12 | retry after a failed refresh (scheduler stopped mid-way) | idempotent |
| A13 | PK change (`order_id` update) | delete old + insert new |
| A14 | the #49 5-order case and #50 cases A/B | match `reducer_model_truth_table.json` |
| A15 | forced RLS as `ax_api` for 2 tenants, plus a cross-shard tenant | each sees only its own rows |

Composite keys are covered by the schema (`(tenant_id, order_id)`). NULL keys are impossible (NOT NULL PK); this is recorded as N/A rather than tested.

**Oracle:**
- After quiescence and catch-up (every stream table's frontier ≥ the last commit LSN), run the three-table `EXCEPT ALL` source-vs-stream oracle (`ax.oracle_mismatches()`), recording missing **and** extra groups.
- Then compare the API against source SQL for summary, day and hour trends, Top-N and both breakdowns (`app/tests/api_oracle.py`).

**Strategy checks:**
- Capture `pgt_refresh_history` (action, `merge_strategy_used`) for every refresh in the run.
- **FAIL the run if any FULL refresh or reinitialisation happened inside a case**, because that would mask a delta defect.

**Separation:** (a) prevention means the PR #58 runtime proof; (b) detection means the low-memory oracle on persisted data; (c) repair means B-2 rebuild or FULL refresh, per stream table, with **separate approval**.

## B. G1 latency (10M fixture, read-only HTTP)
- **Coverage:** 4 families × {largest, median, smallest, top-skew tenant} × {1 h, 1 d, 7 d, 30 d, 90 d, unaligned partial, empty range} × grain day/hour.
- **Samples:** ≥ 200 measured per scenario after 10 warm-up requests, with raw per-request samples saved.
- **Concurrency:** 1, 4 and 8 clients; record offered vs achieved requests/s and 2xx/4xx/5xx/timeouts (2 s timeout).
- **Worst-case analysis:** `EXPLAIN (ANALYZE, BUFFERS)` of the largest-tenant 90 d Top-N, split into stream-table and raw-edge parts. Separate pool wait, B-3 slot wait and JSON serialisation using server-side timing.
- **Verdict:** per scenario, p95 < 200 ms means Great and < 1 s means Good. Report p99 and max beside it.

## C. G2 freshness
- **Mutations:** insert, status update, cancel, refund, delete. Each probe uses a unique order and predicts the **exact** expected `/summary`, `/top-products` and `/breakdown` values. Timing starts right after COMMIT, and the API is polled at 250 ms.
- **Rates:** idle, 5, 20 and 50 writes/s, with a bounded dashboard load of 5 requests/s. At least 20 probes per kind per rate, with a predeclared 30 s Great and 300 s Good timeout. **A timeout counts as a failure.**
- **Recorded:** scheduler dispatch, refresh mode, FULL fallbacks, CDC backlog rows, CPU and memory.
- **Expected:** until G4 is fixed, the A2-type probes can *never* reach the exact value. They are recorded as FAIL(G4), not omitted.

## D. G3 database safety
- **Arms:** A = maintenance on, no dashboard; B = A + a fixed dashboard HTTP rate; C = no maintenance.
- **Design:** five randomised AB/BA pairs, the same fixture, image, config, duration and warm-up, with the client on a separate host (or pinned CPUs).
- **Metric:** normal-app query and transaction p50/p95/p99, TPS offered vs achieved, errors, lock waits, refresh age and FULL fallbacks.
- **Slowdown** = (B − A) / A on the same statistic.
- **A run is confounded** (and excluded) if it has a host freeze (> 1 s scheduler gap without load reason), swap growth, a client CPU > 80 %, or any FULL/DIFFERENTIAL mismatch between arms.

## E. G5 growth
Same harness, settings and image at 1M and 10M. Pair scenarios by role and **also** by a rows-matched tenant (≈ 10× the rows). Compute ratios from raw p95s, and show all 72+ ratios.

## F. FR regression extras
- **FR2:** zero buckets (empty hours), `[from, to)` exclusivity at exact bucket edges, a leap day (synthetic 2028-02-29 window, empty), and DST (UTC-only API: document it).
- **FR3:** a rank change between days and ties.
- **FR5:** forged or expired cookie, cross-tenant read and write, operator vs tenant, and pooled connection reuse (two tenants alternating on one pool, `ax.tenant_id` is transaction-local).

## Bonuses
- **B2:** disposable stack only.
- **B3:** fairness under load (concurrency 8 for one tenant, latency of another).
- **B4:** `live_b4_check.py`.
- **B5:** monitoring values vs the measured harness numbers; degraded state shown truthfully.
