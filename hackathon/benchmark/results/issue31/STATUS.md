# Issue #31 — PARTIAL, scale blocked, small-demo correctness failure

Run: [20261101-fedora](20261101-fedora/). Captured 2026-10-31 UTC / 2026-11-01 IST.
Base: `c19b89a24370d29412fc42c250a86b0ea68f791f`; preserved demo source is the earlier
`2cc3a75` build, not a newly deployed latest-main service.

Executed: offline benchmark/acceptance tests, sharding and mocked fault fixtures;
16 serial read-only HTTP analytics requests plus one warmup; bounded SQL reads
inside READ ONLY transactions with two-second statement timeouts. No stack/load
or write trial was started. HTTP 16/16 succeeded, zero errors/timeouts; pooled
p50 3.459352 ms, p95/p99 12.227789 ms (nearest rank). This is eight scenarios,
two samples each, with at most ten offered requests/s and 9.52 completed/s.
No cold-cache claim; one warmup only. These pooled statistics do not qualify G1.

Selected API numeric comparisons: 16/16 matched the independent raw-source
recomputation. All three streams were compared in one REPEATABLE READ snapshot:
day-product **0 missing / 1 extra**, day-category **0/0**, hour-category **0/0**.
Extra: tenant 2, product 116, paid, UTC day 2026-10-31, order_count 1,
units 1, sales_cents 14094. G4 snapshot status **FAIL**. No rebuild or refresh
was issued; no engine root cause established. The API subset did not exercise
this affected interval/tenant pair. No guarantee that external writers were quiesced.

The initial comparator execution had duplicate unaliased SQL count columns and
raised KeyError after saving evidence. Its original `sql/` artifacts are retained;
`sql-corrected/` is authoritative, with explicit column aliases and confirmed drift.
The corrected comparator exits 1 for mismatch. This was a harness defect repaired
without modifying any database object. Future raw read snapshots must not be
confused with a proven post-quiescence acceptance trial.

Historical Mac 100k/10 and 1M/10 results were traced to
`hackathon/integration/scale/README.md` (0.8/3.9 s load, 104/648 MB,
reported 0/0/0 reconciliation). These are repository-documented historical claims;
no raw 1M HTTP artifact or independent rerun is available. No standalone offline
generator tests were found; live reproducibility tests require an approved target.

Current host: Fedora 44, Intel i3-1115G4, 4 logical CPUs, 7.5 GiB RAM;
available RAM fluctuated 1.1–1.6 GiB; swap used 5.9–6.4 GiB of 7.5 GiB.
228 GiB free on /home. Active swap I/O observed. This fails the proposed >=4 GiB
available-RAM preflight. Do not run another database stack here now.
All 10k/100k/1M stages skipped; 10M prohibited. No Mac resource consumed.

New tests: 25 total benchmark tests (16 acceptance + 9 added), plus sharding 18,
mock library 11, mock demo 7 passed. See raw test log. `just fmt` then `just lint`
were attempted after code changes; both blocked: `just: command not found`.
No zero-warning Rust lint claim. No Rust or SQL-facing application change.

G2 Fedora NOT TESTED: no mutation target authorized. Latest PR #46 now supersedes
the earlier aborted fixture run: 5 matched pairs, G3 still INCOMPLETE, 18/20
freshness probes >30s timeout; 107 FULL fallbacks. Do not infer a Good freshness
pass from a 30s-censored sample. G5 NOT TESTED.

Runtime image inspection records both multiarch index `94344bb9…` and platform
digest `92f271e2…`; PostgreSQL 18.6 / pg_trickle 0.108.3. Configured DIFFERENTIAL,
effective NO_DATA at inspection. Retained history contains DIFFERENTIAL 9,
FULL 3, NO_DATA 61202, REINITIALIZE 3, all completed; this is a historical snapshot,
not a run-scoped differential-maintenance proof.

Safety: 8093/8094, database data, roles, RLS, volumes and running containers were
not mutated/restarted. API requests naturally affect process counters and DB reads;
no claim of zero runtime observation effects. Authentication bypass was already on;
this run does not validate cookie enforcement or negative tenant isolation.

Next: independently diagnose the preserved extra aggregate row using bounded
read-only evidence; arrange a resourced, explicitly approved disposable target
before any mutation or scale run. See [runbook](BENCHMARK_RUNBOOK.md) and
[scorecard](20261101-fedora/G1_G5_SCORECARD.md). Issue #31 stays open.
