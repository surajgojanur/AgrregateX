# AgrregateX — 3–5 minute judge walkthrough

## 0:00–0:30 — Problem and landing page

**Show:** `http://127.0.0.1:8093/`.

**Say:** “A multi-tenant commerce system has operational orders and repeated
analytics requests. If every dashboard repeatedly scans the order table, the
same work competes with writes. AgrregateX keeps tenant-scoped summaries fresh
using PostgreSQL stream tables maintained by pg_trickle, then serves trends,
totals, rankings, and breakdowns through a small API.”

Then select **OPEN DASHBOARD**. State that the local demo is an operator-mode
localhost setup and uses representative data.

Whiteboard version:

```text
Tenant request → API authorizes tenant → route to its database
                                      → pg_trickle stream tables
                                      → summary / trend / Top-N / breakdown
```

The stream tables live in PostgreSQL. `pg_trickle` is the upstream
incremental-view engine; AgrregateX supplies the tenant-aware schema, oracle,
API/routing, UI, monitoring, and demo harness around it.

## 0:30–1:35 — Tenant Analytics

**Show:** tenant selector, time range, **Sales by day**, **Top 10 products**,
category/status breakdown, and freshness panel.

**Say:** “These are the four query families: counts/totals, time trends,
Top-N, and category or status breakdown. The selected tenant is routed through
the API, and the summary uses maintained stream-table ranges with raw reads at
partial time-window edges. The freshness label is based on the latest
completed refresh, not an estimate from a stale-timestamp field.”

Do not press **Insert order** or **Cancel that order**. Writes are disabled.
Freshness shown here is a live point-in-time read, not a commit-to-visible
latency trial.

## 1:35–2:15 — pg_trickle Engine

**Show:** stream-table status, effective refresh modes, recent refresh history,
fallback/failure counts, and change-buffer estimates.

**Say:** “The three active stream tables cover day/product/status,
day/category/status, and hour/category/status. The engine page reads actual
pg_trickle catalog and refresh-history data. Differential maintenance reduces
repeated analytics work, but it also has measurable write overhead in our
recorded load tests; this is an active limitation, not hidden.”

Avoid claiming that every refresh is differential solely from the requested
mode. Point to the displayed **effective** mode and history.

## 2:15–2:45 — Shards

**Show:** `/app#/shards`.

**Say:** “This Fedora environment is configured with one healthy `DEFAULT`
shard and 1,002 orders, including 1,000 seed orders. It does not pretend there
are two shards. The separate Mac demonstration is where two-shard routing and
failure recovery are being prepared.”

## 2:45–3:20 — Live Monitoring

**Show:** `/app#/monitoring`.

**Say:** “Monitoring shows actual API process metrics and refresh data. It
currently marks the shard degraded because the pg_trickle health-check view
returns a permissions error, even though the database probe and Shards page
show the single database reachable and active. That mismatch is a real issue
we have documented. Request metrics are process-local and reset on restart;
CDC backlog is an estimate.”

## 3:20–4:20 — Evidence and limits

**Show:** `hackathon/docs/fedora-evidence/RESULTS.md` and the linked recorded
benchmark files.

**Say:** “The live Fedora API checks and a direct, tenant-RLS-scoped read-only
SQL count agree at 1,002 total and 1,000 seed orders. That verifies this small
demo snapshot, not the official datasets. The recorded exploratory Mac test
shows throughput regressions: about 28% in the single-database P1 experiment
and about 52% under dashboard load in a separate two-shard experiment. We do
not claim the official latency, freshness, database-safety, correctness, or
growth targets at 1M/10M.”

## 4:20–5:00 — Close

**Say:** “The useful idea is to keep analytics reads off repeated full scans
while preserving tenant-scoped results and a correctness oracle. The next
engineering gate is to reduce refresh/write overhead and complete matched,
organizer-compatible scale tests. The current Fedora walkthrough proves the
single-database app path; the Mac two-shard outage/recovery walkthrough is a
separate, pending demo.”

## Judge Q&A (short, defensible)

**Why not add indexes or Redis?** Indexes help individual scans; Redis can
reuse cached answers but needs invalidation and does not calculate incremental
deltas. The current prototype tests maintained aggregates in PostgreSQL, but
our recorded write-overhead results show it is not yet a proven production
winner.

**How do you prevent tenant leakage?** The API authorizes before routing, sets
`ax.tenant_id` transaction-locally, and the non-owner API role is constrained by
forced row-level security. This local operator-bypass session is not itself a
security proof; cite the separate isolation tests for that claim.

**Is it correct?** The test suite has a direct SQL oracle using both-way set
difference for all three stream tables. Fedora's current check compared direct
source counts to shard totals only; it did not re-run the full stream-table
oracle during this read-only demo audit.

**Does it meet the performance scorecard?** Not yet. Official 1M/10M tests
were not run, and recorded throughput regressions fail the database-safety
target.

**What if a shard fails?** The API is designed to return explicit 503 for a
request routed to an unavailable shard without silently reading another
shard. The Fedora environment has only one configured shard; the separate live
partition acceptance remains pending.
