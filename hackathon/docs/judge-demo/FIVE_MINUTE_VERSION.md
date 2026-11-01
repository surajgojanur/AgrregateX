> FINAL REHEARSAL UPDATE — 2026-11-01, HEAD daefdd657339ca9e44805283108610a44ee50009: localhost8093 restored against preserved round1-db. HTTP verified, browser unavailable. Fresh oracle: product/day/status 0 missing, 1 extra; other two 0/0. Current correctness NOT READY. See FINAL_READINESS.md; this update supersedes historical availability/count/readiness statements below.

> Audit revision: `daefdd657339ca9e44805283108610a44ee50009`; 2026-11-01. Recorded evidence retains its own earlier provenance. Current localhost:8093 unavailable. No live feature certified ready.

# Five-minute clock

## 0:00–0:40 — Member 1

“Imagine one hundred businesses sharing ten million orders. Each wants instant analytics, while checkout and order updates must keep working. Every repeated scan competes with that operational work. Our challenge is not just a fast chart: it is fast, fresh, correct and isolated answers without overloading the database. AgrregateX explores maintained analytics inside PostgreSQL. Today we will show the product and the evidence, including where it falls short.”

**Action:** Screen01

## 0:40–1:20 — Member 1

“A client calls FastAPI. The API checks the tenant, then a versioned directory selects its PostgreSQL database. pg_trickle maintains three summaries: day by product and status, day by category and status, and hour by category and status. Our API combines complete summary buckets with raw queries at partial time boundaries. Indexes help scans; caches need invalidation; full materialized-view refresh repeats work. Incremental maintenance processes changes, but adds write cost. The engine is upstream pg_trickle. Our work is the tenant schema, routing, authorization, API, dashboard, oracle and operational tooling.”

**Action:** Screen03; cut comparison examples

## 1:20–2:15 — Member 2

“These are the four required query families: counts and totals, hourly or daily trends, top ten products, and category or status breakdowns. In a rehearsed live session I change the date range, then tenant one to tenant two, and compare the returned results. In this recorded view, those interactions are not a new live test. The React dashboard calls our REST API, whose SQL reads PostgreSQL. Our recorded Fedora snapshot contains one thousand and two orders across ten tenants. That is representative demo data, not the official ten-million-row dataset. A tenant selector demonstrates routing and presentation; it does not prove authorization.”

**Action:** Screen02 recorded or rehearsed live

## 2:15–2:55 — Member 2

“Tenant authorization precedes routing; forced RLS and transaction-local context add database protection. This operator recording is not a live security proof. The recorded outage shows explicit 503 rather than cross-shard fallback.”

**Action:** Screens04–05

## 2:55–3:40 — Member 1

“These SQL definitions are real maintained tables, not frontend fixtures. Our strongest check calculates the answer twice: once from original orders and once from maintained summaries. The independent SQL oracle uses EXCEPT ALL in both directions, checking missing and extra rows for all three summaries. Compare after writes are quiesced and refresh has caught up; otherwise different snapshots can disagree. This recorded rebuild test reports zero missing and extra rows on both shards. A separate API oracle reports two hundred comparisons with zero mismatches. These bounded results do not establish correctness forever. If a new oracle disagrees, we show the failure and investigate; we do not relabel stale or wrong results as correct.”

**Action:** Screen07; show E2/E3

## 3:40–4:20 — Member 2

“Refresh age and commit visibility are different. Small recorded probes were fast, but the current service is unavailable and monitoring repair is held. Official scale remains untested.”

**Action:** Screens08–09

## 4:20–5:00 — Member 1

“Recorded write throughput regressed roughly twenty-eight percent in one experiment and fifty-two percent in another. We must fix database cost and run matched official scale tests. Our contribution is the tenant-aware product and verification around upstream pg_trickle. Thank you.”

**Action:** Screen10

Reserve pauses by dropping comparison sentences; never rush beyond five minutes.
