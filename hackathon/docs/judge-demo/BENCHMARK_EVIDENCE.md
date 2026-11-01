> FINAL REHEARSAL UPDATE — 2026-11-01, HEAD daefdd657339ca9e44805283108610a44ee50009: localhost8093 restored against preserved round1-db. HTTP verified, browser unavailable. Fresh oracle: product/day/status 0 missing, 1 extra; other two 0/0. Current correctness NOT READY. See FINAL_READINESS.md; this update supersedes historical availability/count/readiness statements below.

> Audit revision: `daefdd657339ca9e44805283108610a44ee50009`; 2026-11-01. Recorded evidence retains its own earlier provenance. Current localhost:8093 unavailable. No live feature certified ready.

# Scorecard: no official target qualified

| Target | Recorded value | Conditions / verdict |
|---|---|---|
|Query <200 ms|E5 route p95 6.0–9.8 ms, n=100 each|Small Mac run; dataset provenance incomplete for official comparison; NOT QUALIFIED|
|Freshness <30s|E5 maxima 1852.9/1537.0 ms, n=10/shard|Recorded visibility probe, not refresh-age metric; NOT QUALIFIED|
|DB slowdown <10%|E6 TPS 2457.8 →1760.5, −28.4%; separate sharded run −52.3%|Fails in recorded experiments; not official workload qualification|
|All answers match|E2 three-stream 0/0 both shards; E3 200 comparisons zero mismatches|Bounded quiesced recorded checks; not universal correctness|
|1M→10M latency <2×|No complete paired result|NOT TESTED|

E1 gives Apple M1, PG18.6/pg_trickle0.108.3, 100k representative rows for the single-DB exploratory trial, four clients for 20 seconds; sharded experiment shares one laptop with API/generator/databases and uses two repetitions. Do not assign the single-DB dataset to E5 without corroboration. Fedora E1 has 1,002 orders/10 tenants and individual GET times, not percentiles. Evidence files and provenance: AUDIT_AND_EVIDENCE.md.

Spoken scorecard: “Small recorded reads are fast; official scale remains untested. Maintenance imposed substantial write cost. We must reduce that cost before claiming database safety.”

Improve query target with explain plans and realistic concurrency; freshness with scheduler/backlog diagnosis; safety with matched A/B repeated trials separating no summaries, maintenance only and dashboard reads; correctness with settled snapshots plus mutation coverage; growth with identical skew/queries/hardware at 1M/10 and 10M/100. Report p50/p95/p99, throughput, errors and resource usage. One 20-ms response proves availability only. Benchmark runners mutate/load data: inspect protocol.md and acceptance.py offline, never execute them during judging.
