# AGGREGATE_DELTA_TRACE — NOT COLLECTED

No runtime producer/delta/apply was executed. No MERGE, DELETE+INSERT, vectorized
or P5 path is asserted to have run in this experiment.

Prepared diagnostics enable log_delta_sql (DEBUG1) and log_merge_sql in the
disposable refresh transaction. Capture resolved SQL, source substitutions,
frontiers, PID and plan identity; do not equate a cached/template SQL string with
an executed operation. No manually reconstructed/replayed query is a substitute
for the actual producer, especially after target application changes group state.

For observed DELETE+INSERT, try same-backend pre-COMMIT SELECT from
`pg_temp.__pgt_delta_<pgt_id>` to capture the actual materialized final action
and per-group count/units/cents, including auxiliary counts. This is aggregate
target-state output, not necessarily a raw arithmetic +/− stream: an existing
group can be represented by I(new state) to update it, and disappearance by D.
Use old/new group values to derive signed effects explicitly.

For pure MERGE the delta may not be materialized. If absent, trace_refresh.sql
reports a blocker and rolls back; do not call missing rows an empty delta.
On the disposable target only, evaluate existing nested-statement tracing
(e.g. auto_explain if already installed and separately admitted) for actual SPI
apply plans and affected row counts. Full statement logs alone may miss SPI DML.

If sufficient row/apply observations are unavailable, stop this subtask and
request narrowly scoped instrumentation: immediately before application expose
the actual producer output with group identities/actions/counts/units/cents and
old target values; log the selected strategy and actual affected rows. Instrument
the chosen producer (P5/vector/standard) rather than assuming one. Capture the
exact executed DELETE/INSERT or MERGE and transaction outcome. Do not add target
triggers to observe it: they can force another apply path. No custom build or
instrumentation has been performed or approved.
