# PRD and bonus evidence matrix

**Legend:** `VERIFIED` means the stated narrow behavior has direct evidence;
`PARTIALLY IMPLEMENTED` means code exists but full acceptance is incomplete;
`FAILED` means recorded evidence misses a target; `NOT TESTED` means no valid
result. A small live smoke check never qualifies an official scale target.

## Functional requirements

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

## Performance scorecard (G1–G5)

Targets from `ps_documentation.md` §6; official datasets are 1M rows/10 tenants
and 10M rows/100 tenants, including skew.

| ID / status | Great target | Actual evidence | Assessment |
|---|---:|---|---|
| G1 query latency — NOT TESTED | HTTP query <200 ms | Fedora single samples for analytics routes were 5.0–20.7 ms on 1,002 rows; recorded Mac experiments are representative, not official scale. | No p50/p95 under official dataset/load. Do not claim pass. |
| G2 freshness — NOT TESTED | commit-to-visible <30 s | Fedora refresh ages were under 6 s during page capture; no write was committed. Historical idle Mac insert/cancel values are in `lag-diff-1s-idle.json`. | Refresh age is not commit-to-visible latency. No sustained-write target proof. |
| G3 database safety — FAILED (recorded exploratory runs) | OLTP slowdown <10% | Mac single DB −28.4% throughput (`oltp-A/B.txt`); separate Mac two-shard dashboard-load −52.3% (`oltp-delta-shard-a.txt`). | Material regression. Different experiment arms and shared-hardware confounding are disclosed; neither qualifies official G3. |
| G4 correctness — PARTIALLY IMPLEMENTED | All API answers match SQL oracle | Three-table `EXCEPT ALL` oracle exists in `hackathon/sql/30_oracle.sql`; unit and prior Mac live oracle evidence. Current Fedora `ax_api` source counts (1,002/1,000) match `/api/shards`. | Current Fedora did not execute the three-table oracle or compare all four API answer families; no official scale run. |
| G5 growth — NOT TESTED | Latency ratio 10M/1M <2× | No matched official 1M-vs-10M samples. | Do not infer from 1k/100k representative data. |

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
- **Not run / blocked:** official datasets, G1/G2/G4 full acceptance, G5,
  current Fedora write-path testing, secure-mode live auth tests, and live
  two-shard fault/recovery on this host.

## Hardware and safety context

Fedora host at capture: 7.5 GiB RAM, about 1.3 GiB available, 7.5 GiB swap
with about 4.4 GiB used. Existing services were retained. The API PID 689077
already served on loopback port 8093. Because the machine was memory pressured,
no new database stack, build, load generator, or benchmark was started.
