> FINAL REHEARSAL UPDATE — 2026-11-01, HEAD daefdd657339ca9e44805283108610a44ee50009: localhost8093 restored against preserved round1-db. HTTP verified, browser unavailable. Fresh oracle: product/day/status 0 missing, 1 extra; other two 0/0. Current correctness NOT READY. See FINAL_READINESS.md; this update supersedes historical availability/count/readiness statements below.

> Audit revision: `daefdd657339ca9e44805283108610a44ee50009`; 2026-11-01. Recorded evidence retains its own earlier provenance. Current localhost:8093 unavailable. No live feature certified ready.

# Two-minute emergency pitch

**0:00–0:30 Member 1:** “Imagine one hundred businesses sharing ten million orders. Their dashboards must be fast without slowing checkout. AgrregateX explores maintained tenant summaries in PostgreSQL, served through FastAPI and React. The incremental engine is upstream pg_trickle; we built the tenant schema, API, routing, dashboard and independent checks.”

**0:30–1:00 Member 2:** “Our four query families cover totals, trends, top products and breakdowns. Authorization precedes shard routing, and transaction-local tenant context plus forced row-level security constrain database reads. The current service is unavailable, so these are dated product screenshots, not a live security test.”

**1:00–1:30 Member 1:** “Recorded tests include a three-summary raw-SQL oracle with zero missing and extra rows after rebuild on two shards, and a separate two-hundred-comparison API check. A recorded outage returned explicit failure for the affected shard while the other continued. One laptop is not high availability.”

**1:30–2:00 Member 2:** “We have not completed the official ten-million-row benchmark. Recorded experiments expose substantial write-throughput regressions, so database safety remains unresolved. Our next work is maintenance-cost reduction and matched scale testing. We can explain what works, what is unproven, and how we will verify the next step. Thank you.”

Hold each slot; about 250 words leaves room for pointing at offline evidence.
