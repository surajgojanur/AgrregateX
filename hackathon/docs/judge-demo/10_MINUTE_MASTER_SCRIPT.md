> FINAL REHEARSAL UPDATE — 2026-11-01, HEAD daefdd657339ca9e44805283108610a44ee50009: localhost8093 restored against preserved round1-db. HTTP verified, browser unavailable. Fresh oracle: product/day/status 0 missing, 1 extra; other two 0/0. Current correctness NOT READY. See FINAL_READINESS.md; this update supersedes historical availability/count/readiness statements below.

> Audit revision: `daefdd657339ca9e44805283108610a44ee50009`; 2026-11-01. Recorded evidence retains its own earlier provenance. Current localhost:8093 unavailable. No live feature certified ready.

# Ten-minute master script

Stage clock is authoritative. Member 1 speaks 6:00; Member 2 speaks 4:00. One speaker at a time. Member 2 controls browser; Member 1 controls evidence terminal. Default today: HTTP-backed product available, browser interaction pending; correctness uses explicit fresh failure plus labelled historical evidence. Never wait more than five seconds for a command.

## 00:00–00:45 — Screen 01 — Member 1

**SAYS:** “Imagine one hundred businesses sharing ten million orders. Each wants instant analytics, while checkout and order updates must keep working. Every repeated scan competes with that operational work. Our challenge is not just a fast chart: it is fast, fresh, correct and isolated answers without overloading the database. AgrregateX explores maintained analytics inside PostgreSQL. Today we will show the product and the evidence, including where it falls short.”

**ACTION / SCREEN:** Landing screenshot; open dashboard if rehearsed. Other member operates only while silent.

**JUDGES / EVIDENCE:** Problem and FR1–7; PRD transcription. See AUDIT_AND_EVIDENCE.md.

**TRANSITION:** “Now let us follow one request.”

**TIME / FALLBACK:** Keep this exact clock slot; spend remaining time pointing to evidence. If late, omit the last explanatory sentence before transition; use recorded screen immediately.

## 00:45–01:40 — Screen 03 — Member 1

**SAYS:** “A client calls FastAPI. The API checks the tenant, then a versioned directory selects its PostgreSQL database. pg_trickle maintains three summaries: day by product and status, day by category and status, and hour by category and status. Our API combines complete summary buckets with raw queries at partial time boundaries. Indexes help scans; caches need invalidation; full materialized-view refresh repeats work. Incremental maintenance processes changes, but adds write cost. The engine is upstream pg_trickle. Our work is the tenant schema, routing, authorization, API, dashboard, oracle and operational tooling.”

**ACTION / SCREEN:** Show diagram and E8 definitions. Other member operates only while silent.

**JUDGES / EVIDENCE:** Architecture and attribution. See AUDIT_AND_EVIDENCE.md.

**TRANSITION:** “Here is what those summaries serve.”

**TIME / FALLBACK:** Keep this exact clock slot; spend remaining time pointing to evidence. If late, omit the last explanatory sentence before transition; use recorded screen immediately.

## 01:40–03:05 — Screen 02 — Member 2

**SAYS:** “These are the four required query families: counts and totals, hourly or daily trends, top ten products, and category or status breakdowns. In a rehearsed live session I change the date range, then tenant one to tenant two, and compare the returned results. In this recorded view, those interactions are not a new live test. The React dashboard calls our REST API, whose SQL reads PostgreSQL. Our current Fedora database contains one thousand and three orders across ten tenants. That is representative demo data, not the official ten-million-row dataset. A tenant selector demonstrates routing and presentation; it does not prove authorization.”

**ACTION / SCREEN:** Show analytics screenshot; conditional live date/tenant changes; API proof. Other member operates only while silent.

**JUDGES / EVIDENCE:** FR1–4/7; E1/E8. See AUDIT_AND_EVIDENCE.md.

**TRANSITION:** “So let us examine the security boundary.”

**TIME / FALLBACK:** Keep this exact clock slot; spend remaining time pointing to evidence. If late, omit the last explanatory sentence before transition; use recorded screen immediately.

## 03:05–04:10 — Screen 04 — Member 2

**SAYS:** “The API authorizes a tenant before routing. A signed demo session identifies the user; this is not production identity management. Each database transaction sets tenant context locally, and forced row-level security constrains the nonprivileged API role on source and summary tables. Transaction-local context prevents a pooled connection from carrying a previous tenant context into the next transaction. The recorded bonus tests include operator-only access returning forbidden. Our Fedora capture used operator bypass, so it is not a tenant-login security proof. A fresh secure-mode cross-tenant 403 remains a rehearsal gate; we will not fake it here.”

**ACTION / SCREEN:** Show auth.py, db.py, 20_security.sql; recorded E2. Other member operates only while silent.

**JUDGES / EVIDENCE:** FR5; distinguish implementation from live negative test. See AUDIT_AND_EVIDENCE.md.

**TRANSITION:** “Isolation also has to survive routing failures.”

**TIME / FALLBACK:** Keep this exact clock slot; spend remaining time pointing to evidence. If late, omit the last explanatory sentence before transition; use recorded screen immediately.

## 04:10–05:10 — Screen 05 — Member 1

**SAYS:** “The Fedora recording has one default shard. Separately, this Mac log records two physical PostgreSQL databases. During the recorded outage, requests owned by shard A returned an explicit 503, while shard B continued serving. The router did not silently read another tenant database. After recovery, the log checks the source against the aggregate. We will not disconnect anything during judging. Two databases on one laptop demonstrate routing and failure behavior, not high availability. Directory versioning identifies a routing configuration; it does not implement online tenant migration.”

**ACTION / SCREEN:** Show E4 selected lines and directory.v1.json. Other member operates only while silent.

**JUDGES / EVIDENCE:** Failure semantics; E4/E8. See AUDIT_AND_EVIDENCE.md.

**TRANSITION:** “But an available answer must also be correct.”

**TIME / FALLBACK:** Keep this exact clock slot; spend remaining time pointing to evidence. If late, omit the last explanatory sentence before transition; use recorded screen immediately.

## 05:10–06:25 — Screen 06–07 — Member 1

**SAYS:** “These SQL definitions are real maintained tables, not frontend fixtures. Our strongest check calculates the answer twice: once from original orders and once from maintained summaries. The independent SQL oracle uses EXCEPT ALL in both directions, checking missing and extra rows for all three summaries. Compare after writes are quiesced and refresh has caught up; otherwise different snapshots can disagree. This recorded rebuild test reports zero missing and extra rows on both shards. A separate recorded API oracle reports two hundred comparisons with zero mismatches. Today’s fresh SQL oracle found one extra product-summary row; the other two summaries matched. We are preserving that failure and withdrawing current correctness claims. These bounded results do not establish correctness forever. If a new oracle disagrees, we show the failure and investigate; we do not relabel stale or wrong results as correct.”

**ACTION / SCREEN:** Show E2 oracle and E3; SQL source. Other member operates only while silent.

**JUDGES / EVIDENCE:** Correctness; FR6 bounded evidence. See AUDIT_AND_EVIDENCE.md.

**TRANSITION:** “Freshness is the next separate question.”

**TIME / FALLBACK:** Keep this exact clock slot; spend remaining time pointing to evidence. If late, omit the last explanatory sentence before transition; use recorded screen immediately.

## 06:25–07:35 — Screen 08–09 — Member 2

**SAYS:** “The freshness panel reports the age of completed refresh evidence. That is different from timing an order commit until its result becomes visible. The recorded two-shard measurements contain ten visibility samples per shard, with maxima around one point nine seconds. This is a small recorded experiment, not a sustained thirty-second guarantee. Monitoring exposes refresh history, backlog estimates and process-local API measurements. The older screenshot shows degraded health; the newer audit says the view grant alone did not fix all dependencies. The repair proposal is held for review. We show that limitation instead of manufacturing a green status. We also keep writes and rebuilds out of this stage demo.”

**ACTION / SCREEN:** Show E5 and monitoring screenshot labelled historical; E7. Other member operates only while silent.

**JUDGES / EVIDENCE:** B1/B5 and operational honesty. See AUDIT_AND_EVIDENCE.md.

**TRANSITION:** “Now let us put performance in context.”

**TIME / FALLBACK:** Keep this exact clock slot; spend remaining time pointing to evidence. If late, omit the last explanatory sentence before transition; use recorded screen immediately.

## 07:35–09:10 — Screen 09 — Member 1

**SAYS:** “The official great targets are under two hundred milliseconds for queries, under thirty seconds freshness, under ten percent database slowdown, matching answers, and less than twice the latency as data grows from one to ten million. We have not completed that official scorecard. Our small recorded API experiment has route p95 values below ten milliseconds, but a fast sample is not a sustained scale result. More importantly, the recorded single-database experiment drops from about twenty-four hundred fifty-eight to seventeen hundred sixty-one transactions per second: roughly twenty-eight percent. A separate two-shard shared-laptop experiment drops about fifty-two percent. Those workloads differ, so do not combine them into one benchmark. Dashboard reads, trigger capture, refresh work and laptop contention need separate measurement. Our next gate is a matched baseline, maintenance-only and dashboard-load experiment with repeated runs, equal resources and correctness checks, followed by the official skewed datasets. Until then, database safety is an unresolved engineering requirement.”

**ACTION / SCREEN:** Show benchmark scorecard E6. Other member operates only while silent.

**JUDGES / EVIDENCE:** Official targets remain unqualified. See AUDIT_AND_EVIDENCE.md.

**TRANSITION:** “Here is what we would build next.”

**TIME / FALLBACK:** Keep this exact clock slot; spend remaining time pointing to evidence. If late, omit the last explanatory sentence before transition; use recorded screen immediately.

## 09:10–09:35 — Screen 10 — Member 2

**SAYS:** “First, restore a supervised demo process and verify monitoring with least privilege. Then repeat mutation and oracle rehearsals, reduce maintenance overhead, and run the official scale tests. The same tenant-scoped pattern could support cybersecurity event summaries, but security-event ingestion is a future application, not a feature we demonstrated.”

**ACTION / SCREEN:** Show roadmap and attribution. Other member operates only while silent.

**JUDGES / EVIDENCE:** Next steps grounded in gaps. See AUDIT_AND_EVIDENCE.md.

**TRANSITION:** “Our takeaway is simple.”

**TIME / FALLBACK:** Keep this exact clock slot; spend remaining time pointing to evidence. If late, omit the last explanatory sentence before transition; use recorded screen immediately.

## 09:35–10:00 — Screen 10 — Member 1

**SAYS:** “AgrregateX turns repeated analytics work into maintained tenant summaries. We engineered the access path, routing, product and independent checks around an upstream engine. Our evidence shows a working small-data prototype and exposes a real database-cost problem. We know what works, what remains unproven, and the next experiment needed to earn a production claim. Thank you.”

**ACTION / SCREEN:** Hold architecture/evidence summary. Other member operates only while silent.

**JUDGES / EVIDENCE:** Three messages: maintain, isolate, verify. See AUDIT_AND_EVIDENCE.md.

**TRANSITION:** “Stop at 10:00.”

**TIME / FALLBACK:** Keep this exact clock slot; spend remaining time pointing to evidence. If late, omit the last explanatory sentence before transition; use recorded screen immediately.

## Timing review

Roughly 1,100 spoken words including transitions, about 8.5 minutes at 130 words/minute; remaining time covers clicks, pointing and pauses. Rehearse with stopwatch: exact slots total 600 seconds, not a guarantee of human delivery speed. Never fill command delays with more speech; cut examples if needed.
