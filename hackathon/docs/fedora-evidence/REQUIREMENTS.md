# PRD and bonus evidence matrix

**Legend:** `VERIFIED` means the stated narrow behavior has direct evidence;
`PARTIALLY IMPLEMENTED` means code exists but full acceptance is incomplete;
`FAILED` means recorded evidence misses a target; `NOT TESTED` means no valid
result. A small live smoke check never qualifies an official scale target.

## Functional requirements

**Important subsequent G4 evidence (2026-11-01):** the historical Fedora 8093 GET capture below predates detailed G4 forensics. On the preserved 8094 demo, tenant 2/product 116 has an extra `paid` aggregate; summary, Top-N and status breakdown responses are incorrect versus independent source SQL. Do not use earlier visual/smoke PASS results as proof of full FR-1/FR-3/FR-4 correctness. See [G4 forensics](../../benchmark/results/issue31/20261101T2100Z-forensics/REPORT.md), the [observed isolated staging-loss trace](../../integration/g4_trace/REPORT.md) and corrective follow-up [#54](https://github.com/surajgojanur/AgrregateX/issues/54).

| ID / status | What exists and code location | Evidence | Gap / judge-safe statement |
|---|---|---|---|
| FR-1 — PARTIALLY IMPLEMENTED | `/api/tenants/{id}/summary`; `hackathon/app/axapi/main.py`, `queries.py`; Dashboard summary cards | Fedora GET 200; direct SQL count agrees with global shard order total. Existing oracle tests in `hackathon/app/tests/api_oracle.py`. | Current live audit did not compare revenue response to a same-snapshot SQL oracle; organizer sales/cancellation semantics remain unknown. |
| FR-2 — PARTIALLY IMPLEMENTED | Daily/hour trends endpoints and Dashboard chart; `main.py`, `queries.py`, `Dashboard.jsx` | Fedora daily and hourly GET 200; screenshot. | UTC bucketing is the current implementation; organizer timezone rules unknown. No official workload/correctness qualification. |
| FR-3 — PARTIALLY IMPLEMENTED | Top-N endpoint and panel; `main.py`, `queries.py`, `Dashboard.jsx` | Fedora Top-10 GET 200; screenshot. | Current ranking semantics are implementation-specific (sales); organizer tie-breaking/metric not confirmed. |
| FR-4 — PARTIALLY IMPLEMENTED | Status/category breakdown endpoint and panel; `main.py`, `queries.py`, `Dashboard.jsx` | Fedora both breakdown GETs 200; screenshot. | Representative statuses are pending/paid/shipped/cancelled/refunded; organizer's complete list is unknown. |
| FR-5 — PARTIALLY IMPLEMENTED | `auth.py`, `db.py`, `20_security.sql`; per-tenant transaction setting plus forced RLS; cache keys include tenant scope | Existing isolation tests (`test_shards_compatibility.py`, Mac `rls-test.txt`/`rls-source-reinit.txt`). Fedora app is operator bypass; it cannot prove negative authorization. | “Tenant isolation is enforced by code/tests in secure mode; today's localhost operator session is not a security demonstration.” |
| FR-6 — PARTIALLY IMPLEMENTED | pg_trickle differential stream tables; `engine.py` freshness/visibility checks; optional write endpoint disabled in Fedora | Historical Mac idle insert/cancel lag evidence and three-table oracle. | No Fedora mutation or commit-to-visible timing was allowed; no sustained-write freshness claim. |
| FR-7 — VERIFIED (API availability only) | REST routes in `hackathon/app/axapi/main.py`; Vite/static UI | All four live analytics route families returned 200; landing, Dashboard, Shards, Engine and Monitoring rendered. | Endpoint success does not certify official performance/correctness targets. |

## Bonuses

| ID / status | Implementation | Evidence | Limitation |
|---|---|---|---|
| B1 — PARTIALLY IMPLEMENTED | Freshness attached to analytics responses; dashboard and Engine/Shard freshness | Current Fedora freshness and stream-table page live; code in `engine.py`; prior Mac mutation lag in `lag-diff-1s-idle.json`. | No new write/visibility trial; current ages are point-in-time completed-refresh ages. |
| B2 — PARTIALLY IMPLEMENTED | Protected CLI `python -m axapi.rebuild`; `hackathon/app/axapi/rebuild.py` | Prior Mac disposable-stack run in `live-bonus-20261031T132216Z.txt`, with oracle verification. | Not executed against Fedora's working DB; do not demo it here. |
| B3 — PARTIALLY IMPLEMENTED | Per-tenant in-process concurrency cap / 429; `limits.py`, `/api/limits` | Live Fedora limits API/page available; existing unit tests; prior Mac flood test in `live-bonus-20261031T132216Z.txt`. | This run did not flood the service. Limit is per API process, not global across workers. |
| B4 — NOT IMPLEMENTED | No configuration-driven metric registry | `ps_documentation.md` §7 and §17 checklist says not built. | State plainly that B4 is absent. |
| B5 — PARTIALLY IMPLEMENTED | Monitoring/Engine/Shards pages; `monitoring.py`, `engine.py`, frontend pages | Live GET and browser rendering on Fedora. | The page marks the shard degraded because `pgtrickle.health_check()` reports `UNKNOWN` from denied access to `stream_tables_info`; `/api/health` and Shards report reachable/healthy. API latency stats are process-local/in-memory; no persistent history. CDC backlog is estimated. |

## Performance scorecard (G1–G5) — updated 2026-11-01

This matrix supersedes only the earlier **G1–G5 performance** subsection below; original Fedora screenshot and GET-only notes are dated captures. The Mac experimental 1M dataset is representative synthetic, **not** official organizer data. Runtime correctness remains a blocker.

| Goal | PRD Great target | Measured evidence | Judge-safe status |
|---|---|---|---|
| G1 HTTP latency | <200 ms | [Mac 1M/10 synthetic](../../integration/scale/results/REPORT-1m.md): 3,600 serial HTTP requests, 72/72 scenario p95s <200 ms, worst **60.8 ms**, 0 errors; under 5 writes/s worst p95 **81.7 ms** (n=1,440), 0 errors. | **1M preliminary result only**; 10M, official data, concurrent clients NOT TESTED. |
| G2 commit-to-visible | <30 s | Mac 1M with 5 changes/s: n=8 probes, median 18.7 s, max 24 s; Mac 10k at 200 TPS: **18/20 timeouts beyond 30 s**, 107 FULL fallbacks. Fedora write path not tested. | **G2 fails heavier-write Great test**; 1M low-rate sample is encouraging but limited. |
| G3 OLTP safety | <10% slower | Matched five-pair A/B/C run: median B vs A TPS +0.7%, but p95 comparisons confounded by host freezes. Earlier exploratory unbounded load suffered large throughput regressions. | **INCOMPLETE / not qualified**. |
| G4 correctness | All answers match independent SQL oracle | Mac 1M before writer API checks 225/225 and stream oracle 0/0/0; after writer product rollup **16 missing / 31 extra**. Fedora product stream **0 missing / 1 ghost paid**, with wrong summary/Top-N/status. Approved Mac 82-order CDC trace shows raw `I paid,D paid,I cancelled` but post-stage missing negative D; product oracle 0/1, joined 0/0. | **FAIL**: staging loss **observed**, exact reducer-vs-visibility still inferred; diagnostic #50 completed, fix [#54](https://github.com/surajgojanur/AgrregateX/issues/54) open. |
| G5 10M/1M growth | <2× | No matched 1M/10M requests; Mac operator authorized a disposable synthetic 10M/100 attempt but no verified run results are checked in. | **NOT TESTED**. |

Evidence: [G3 matched report](../../integration/g3/results/10k-o200-r20-matched/REPORT.md), [Mac 1M report](../../integration/scale/results/REPORT-1m.md), [Fedora G4 forensics](../../benchmark/results/issue31/20261101T2100Z-forensics/REPORT.md), [original offline protocol](../../benchmark/results/issue31/20261101T2137Z-controlled-prep/RUNTIME_REPRO_REPORT.md), [completed controlled staging trace](../../integration/g4_trace/REPORT.md), [successful two-shard partition drill](../../sharding/results/partition-20261031T231534Z.txt), [Issue #31](https://github.com/surajgojanur/AgrregateX/issues/31).


**New implementation status:** [PR #51](https://github.com/surajgojanur/AgrregateX/pull/51) merged a **default-OFF** server-side `AX_ANALYTICS_READ_MODE=raw_source` alternative using restricted tenant-scoped SQL for the four existing endpoints (55 reported offline tests). It has **no live PostgreSQL proof**, and the React caption is not mode-aware. Activation is BLOCKED pending [#55](https://github.com/surajgojanur/AgrregateX/issues/55), explicit approval and verified security/correctness/performance. The original maintained streams remain wrong; neither #51 nor the successful single-host sharding fault drill fixes G4.

## Provenance categories

- **New Fedora live:** bounded GET-only API checks; Chromium desktop/mobile
  render and reload; one read-only SQL transaction as `ax_api`, target verified
  from the API process configuration, with a 2-second statement timeout and
  tenant RLS set per query. No writes or faults.
- **Previous Mac live:** files under `hackathon/integration/results/`,
  `hackathon/sharding/results/`, and the dated live bonus result above. Treat as
  representative exploratory evidence, not a Fedora run or official dataset.
- **Unit/mock:** `hackathon/app/tests/test_*.py`. These demonstrate tested code
  paths but not production workload performance.
- **Not run / blocked:** official organizer-dataset certification, 10M and matched G5; full G1/G2/G4 acceptance, current Fedora write-path testing, secure-mode live auth tests, and a new live two-shard fault/recovery trial on this host. The Mac synthetic 1M measurements are documented above; they were not repeated on Fedora.

## Hardware and safety context

Fedora host at capture: 7.5 GiB RAM, about 1.3 GiB available, 7.5 GiB swap
with about 4.4 GiB used. Existing services were retained. The API PID 689077
already served on loopback port 8093. Because the machine was memory pressured,
no new database stack, build, load generator, or benchmark was started.
