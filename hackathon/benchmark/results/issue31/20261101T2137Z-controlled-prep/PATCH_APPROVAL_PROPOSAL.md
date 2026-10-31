# Approval packet — reproduction first, patch later

## Immediate decision required

Authorize only the exact disposable target/resources/lifecycle in
RUNTIME_REPRO_REPORT.md after fresh preflight passes. Current host fails RAM and
swap gates; authorization alone cannot override them. No demo service may be
stopped to make room. A different host or teammate stack needs a new exact target
and owner coordination. No automatic retry/launch is scheduled.

Stock diagnostics first, with `primary_default` leaving `aggregate_fast_path`,
`merge_strategy`, and its threshold untouched. The separately labelled
`comparison_fast_off_merge` and `comparison_fast_off_auto` settings are controls,
not the primary result. Source inspection shows the automatic strategy can
choose a path; use the completed refresh-history row's `merge_strategy_used` to
record the actual application. P5 direct aggregate SQL production, B-1
aggregate-fast-path application, vector aggregate execution, PH-D1
DELETE+INSERT, and ordinary MERGE are separate dimensions. See the revised
report and tests.

The existing same-backend script observes only raw buffer copy and (if present)
the post-reducer/post-visibility stage. It cannot prove the reducer's input or
separate RLS visibility pruning. A materialized delta is not guaranteed on MERGE
and its absence is now explicitly INCONCLUSIVE. If stock diagnostics do not
expose the required boundary/output, request diagnostic-only custom-build
instrumentation separately as scoped in STAGING_TRACE.md and
AGGREGATE_DELTA_TRACE.md. Current target approval does not include that build.

Source review of v0.108.3 shows `pg_trickle.enabled=off` disables scheduler
work, while manual `refresh_stream_table` has no master-enabled guard. This is
source-validated but still needs disposable-runtime verification before relying
on it operationally.

## Conditional correction, not authorized or applied

If correct raw events become incorrect during the endpoint reducer, propose the
narrow keyed correction: retain earliest D iff first event D, retain latest I iff
last event I. Thus I/I keeps latestI, I/D keeps none, D/I keeps firstD+lastI,
D/D keeps firstD. Preserve complete payloads, original LSN range and RLS visibility
filtering. Audit equivalent persistent/partitioned reducers; do not apply this
rule to keyless multiplicities or deferred-key histories without separate proof.

If stage is correct but produced delta wrong, do not patch this predicate merely
because it is suspicious. Isolate actual producer/cache path. If delta is correct
but persisted groups wrong, investigate actual apply/identity/frontier instead.
If raw events differ or span windows, correct the capture/window hypothesis first.

## Required review evidence before a Rust correction

- Clean baseline and explicit source-commit/frontier/stage/producer/apply trace.
- All cases in the report's regression matrix, forced RLS, stable composite PK,
  control tenant, three-table independent oracle all0/0 on each clean case.
- Both actual MERGE and DELETE+INSERT paths; no claim from requested GUC alone.
- Existing direct aggregate/scan/CDC pure Rust tests, relevant Testcontainers
  integration/E2E tests for CDC, RLS and aggregate DVM; use repository justfile
  recipes and documented infrastructure. No local PostgreSQL instance.
- `just fmt` then `just lint`, zero warnings; not currently available here.
- Specific safety regressions for shared frontiers, keyless/deferred keys,
  PK/group movement, insert-delete cancellation, auxiliary sums and empty groups
  before claiming support beyond the admitted shape.

Existing drift will survive a prevention-only fix. Any preserved-data repair,
runtime binary deployment, FULL-maintenance setting or source-SQL app fallback
requires a separately reviewed authorization and post-action oracle. Nothing in
this packet approves those operations. Keep PR #48 DRAFT and Issue #31 OPEN.
