# G-3 observations from loader work (proposal input, not a shared change)

The integration owner asked Opus to note G-3 transaction/commit overhead (PR #2 measured a +42.71% mean
full-transaction slowdown under 20 req/s dashboard traffic). Loader measurements give one data point:

* Inserting 1M rows **with** the per-row `rollups` PL/pgSQL trigger took 78.8 s, against 14.9 s with the
  trigger off and the rollups merged from deltas. That is about **64 µs of extra work per source row**,
  measured single-session, uncontended, local PG 17.6, no CPU limit. Each API write pays this inside its
  transaction: two upserts, plus the old and new image for UPDATE, on the hottest rollup rows.
* Under a 1.5 CPU limit with concurrent dashboard reads, this CPU is competing with the reads. That is
  consistent with, but **does not prove**, the trigger being a G-3 contributor.

Suggested experiment, to be owned by Codex or the integration owner:

1. Run the G-3 arm on a fixture copy with `rollups` disabled.
2. Run it again with rollups maintained.
3. The difference attributes the write-path cost to the trigger.

Candidate optimisations, **only if** that experiment shows the trigger matters. Each changes shared schema and
needs agreement on Issue #1:

* a simplified trigger body without the per-call GROUP BY/UNION, e.g. direct upserts with an
  UPDATE fast path when old and new keys are equal;
* statement-level triggers with transition tables for any multi-row write path.

No change has been made.
