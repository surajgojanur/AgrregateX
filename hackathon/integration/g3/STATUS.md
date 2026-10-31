# G3 A/B status: INCOMPLETE (issue #28)

**Not a G3 result.** The full 5-pair run was stopped after 2 of 15 arms (at the user's request to push the work so far).
Everything below is n=1 per arm on one Apple M1 laptop with REPRESENTATIVE data (shard A: 5,013 seed orders), so it is **indicative only**.

| Run | Arm | TPS | OLTP p50 / p95 / p99 ms | Dashboard HTTP (arm B) | max CDC backlog | max refresh age (s) | commit→visible probes (ms) |
|---|---|---|---|---|---|---|---|
| smoke (15 s, seed 1) | B | 1644.0 | 2.13 / 3.76 / 5.92 | 20.0 req/s, 0 errors, p95 12.07 ms | 76728 | 20.5 | insert 13659.1, cancel 1554.6 |
| smoke (15 s, seed 1) | C | 1245.7 | 2.06 / 5.44 / 12.03 | — | 0 | None | — |
| smoke (15 s, seed 1) | A | 1509.0 | 2.18 / 3.94 / 8.43 | — | 31816 | 11.0 | insert 11877.6, cancel 1496.8 |
| 5-pair run, pair 1 (35 s, seed 2801) | C | 1683.0 | 2.06 / 3.73 / 6.23 | — | 0 | None | — |
| 5-pair run, pair 1 (35 s, seed 2801) | A | 822.8 | 3.51 / 9.44 / 20.54 | — | 92338 | 29.8 | insert TIMEOUT, cancel TIMEOUT |

## What this suggests (hypotheses to test, not conclusions)
1. **Dashboard load at a fixed realistic rate (20 req/s) did not reduce OLTP throughput** in the smoke pair (B +8.9% TPS vs A, p95 −4.6%). The earlier −52% (`sharding/results/oltp-delta-shard-a.txt`) used an **unbounded** 4-thread flood (140–350 req/s) that saturated the laptop CPU shared by client, API and database. Different question, different answer; both must be reported.
2. **Incremental maintenance (CDC + refresh) under heavy writes is the bigger cost.** A vs C is inconsistent between the two observations: A was +21% vs C in the smoke run, but in the 5-pair run A was −51% vs C (822 vs 1,683 TPS) with a 92k-row CDC backlog. That needs the full randomised pairs before any claim.
3. **Freshness (G2) degrades under heavy write load.** At about 1,500 OLTP TPS (~3,000 writes/s) the CDC backlog reached 30–92k rows, commit→visible was 12–14 s in the smoke run, and probes **timed out (> 30 s)** in the 5-pair arm A. This links to the open scheduler-stall finding in PR #36 and to PROPOSAL P1 (`docs/proposals/opus/P1-upstream-null-safe-group-join.md`).

## Why the full run was slow
Between arms the harness deletes pgbench's rows and waits (up to 120 s) for the CDC backlog to drain; with a ~90k-row backlog plus 45 s probe timeouts each arm took several minutes. Next run: fewer clients or a rate-limited pgbench (`-R`), so the write rate is realistic and the drain is bounded.

## Next steps (#28)
- Re-run 5 randomised pairs with a rate-limited OLTP workload (e.g. `pgbench -R 300`) at 20 and 100 dashboard req/s; then at 100k orders if memory allows.
- P1: `EXPLAIN (ANALYZE, BUFFERS)` of the delta join (`IS NOT DISTINCT FROM` vs `=`) and low-risk configuration experiments (schedule, workers, CDC mode). **No Rust changes without separate approval.**
- Report with a TEST / DEFER / REJECT recommendation on P1.
