# PROPOSAL P1 — make pg_trickle's aggregate delta join hashable/indexable

**From:** OPUS · **Phase:** P1 · **Status:** PROPOSAL — needs a HUMAN decision (ADOPT / TEST / DEFER / REJECT)
**Touches:** upstream engine `src/dvm/operators/aggregate.rs`. Per the rules this needs explicit human approval before anyone implements it.

## Problem

For every algebraic GROUP BY stream table, pg_trickle 0.108.3 computes the new aggregate state by joining the delta groups to the
existing stream-table rows on **`st.<key> IS NOT DISTINCT FROM d.<key>`** for every group key
(`src/dvm/operators/aggregate.rs:2730`, unconditional; similar shapes at :151, :979, :1320, :1528, :2746).
PostgreSQL can't hash, merge or index-scan `IS NOT DISTINCT FROM`, so the only possible plan is a nested loop over the whole
stream table for each delta group. pg_trickle's own `enable_nestloop=off` hint makes no difference (`Disabled: true` appears in the plan).

## Evidence (observed, Apple M1 / Docker 4 GB, 100k orders, stream table ≈ 88k rows)

| changes queued | refresh total (pg_trickle `[PGS_PROFILE]`) |
|---|---|
| 10 | 96–119 ms |
| 100 | 640–666 ms |
| 1,000 | 4.6–5.2 s |
| 8,730 (burst) | 31 s (plan: `Rows Removed by Join Filter: 243,494,742`) |

Micro-benchmark of the same join shape on the same tables (`results/` and handoff §F3):

| join predicate | plan | time |
|---|---|---|
| `IS NOT DISTINCT FROM` ×4 (current) | Nested Loop, 203.6M rows filtered | **23,076 ms** |
| `=` ×4 | Nested Loop + Index Cond on the auto group-key index | **25 ms** |

PRD consequences, measured at only 100k rows (both are Great-target FAILs):
- **G-3:** OLTP throughput fell from 2,458 to 1,761 tps (**−28%**), with 0 refreshes completing in a 20s run.
- **G-2:** staleness reached 22s and was still climbing. Cost scales with stream-table size, so the 10M case is worse.

## Options

1. **Equality when keys are provably NOT NULL.** Emit `st.k = d.k` when the group key is non-nullable: a NOT NULL base column, or an
   expression over NOT NULL columns with a strict function. This matches PostgreSQL semantics exactly for non-null keys.
2. **Join on the row identity.** `d` already carries `__pgt_row_id` (the MERGE uses it, hashed and indexed through
   `row_probe_v1(__pgt_row_id)`). Join `st.__pgt_row_id = d.__pgt_row_id` and keep the null-safe predicates as a residual filter.
   This is NULL-correct for every key.
3. **Expand the null-safe test** to `(st.k = d.k OR (st.k IS NULL AND d.k IS NULL))`. It is still not hashable in PostgreSQL. **Not recommended.**

Recommendation: **TEST option 2** first, because it covers nullable keys too. Fall back to option 1 if row-id derivation differs on
some paths.

## Minimum A/B experiment (Fedora: it needs a Rust/pgrx build, and the Opus machine has about 6 GB free disk)

1. Build `0.108.4` unchanged as the control, then `0.108.4 + patch`, using `Dockerfile.demo`.
2. For each build, run `hackathon/integration/ab_run.sh DIFFERENTIAL 1s trigger 5000 false`, the pgbench arms A and B, and `lag_probe.py`.
3. Pass criteria: oracle 0/0; audit shows DIFFERENTIAL with no fallback; the 1,000-change refresh is at least 10× faster; arm B
   throughput is within 10% of arm A at 100k, and then at 1M.
4. Run the upstream unit and E2E suites that cover `aggregate.rs` (`just test-unit`, plus the aggregate E2E subset).

## Rollback
The patch lives on a separate branch with a separate image tag. The control image stays the default until the A/B passes.

## Complexity and risk
- **Complexity:** small, about 20–60 lines plus tests, but in correctness-critical DVM code. Every aggregate shape needs the oracle and the upstream E2E suite.
- **Risk:** a wrong NULL-group merge (option 1 if nullability is misjudged).
- **Credit:** this would be an upstream contribution, so offer it to trickle-labs as a PR.

## If REJECTED / DEFERRED
- **C. Separate analytics PostgreSQL via logical replication:** removes refresh CPU from the OLTP host (helps G-3) but not G-2 under load.
- **D. Hand-maintained signed-delta rollups:** keyed `=` upserts, but these previously failed G-3 at about 26%.
- **Batch shaping:** use a 5–10s schedule with `differential_max_change_ratio` tuned, so that large deltas take FULL deliberately.
  FULL took 0.35–0.93s at 100k rows, but grows linearly to roughly 35–90s at 10M. **Not viable at 10M.**
