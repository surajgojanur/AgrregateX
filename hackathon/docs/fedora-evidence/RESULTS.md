# Fedora read-only demo evidence

**Captured:** 2026-10-31 (Fedora host; current branch base `887743430030fb61b1bcef5169fbdaaa8b478525`).
**Service:** existing process PID 689077 on `127.0.0.1:8093`; API database
configuration resolved to loopback `127.0.0.1:25560`, database `aggregatex`.
The API connected to PostgreSQL as non-privileged `ax_api`; PostgreSQL reports
its container-side endpoint as `10.89.3.4:5432`. Local operator bypass was
enabled and demo writes disabled. No container, service, schema, or row was
changed.

## Current live checks

| Check | Result | Evidence / limit |
|---|---|---|
| Landing page and **OPEN DASHBOARD** | PASS | Chromium rendered `/`, clicked the CTA and reached `/app#/dashboard`. |
| Analytics API families | PASS for bounded GET availability | Summary, daily/hourly trends, Top-10, status/category breakdown, freshness all returned HTTP 200 for tenant 1. One request per route; the per-request times below are not p50/p95. |
| Shards | PASS | `/api/shards` and page show one `default` shard, available, complete, 1,002 orders / 1,000 seed orders, and three ACTIVE DIFFERENTIAL tables. No second shard is claimed. |
| Engine, Monitoring, Limits | PASS for bounded GET and render | Operator endpoints returned HTTP 200 and Chromium rendered the pages. These calls are made in local operator-bypass mode. |
| Desktop/mobile layout | PASS for sampled pages | Chromium screenshot capture at 1440×1000 and 390×844. Mobile dashboard and Shards document width was 390 px at 390 px viewport. |
| Browser errors | PASS | No Chromium page errors or console errors captured during this run. |
| Reload | PASS | Dashboard and Shards were reloaded in a new browser context after navigation; both rendered. |
| Direct source count comparison | PASS, bounded and read-only | `ax_api`, `BEGIN READ ONLY`, 2-second statement timeout; transaction-local `ax.tenant_id` set for each tenant; counted rows and `order_id < 100000000` seed rows. Totals matched `/api/shards`. This did not compare every analytics answer or execute the stream-table oracle. |
| Live insert/update/cancel/freshness lag | NOT TESTED | Writes were explicitly prohibited and disabled; no mutation was sent. |
| Secure-mode auth/RLS negative test | NOT TESTED LIVE | The process has `AX_AUTH_DISABLED=1`; use separate tests/evidence, not this operator session. |

**Monitoring limitation observed live:** the page renders but marks the `default`
shard **degraded** because the pg_trickle health check returned `UNKNOWN`
(`permission denied for view stream_tables_info`). At the same time,
`/api/health` returned `ok`, the Shards page showed the database reachable, and
the stream tables were ACTIVE with zero consecutive refresh errors. This is a
monitoring/catalog-permission mismatch; it is not evidence of a network
partition, and this documentation-only task did not change permissions.

### Read-only SQL count by tenant

Seed definition matches `ax.tenant_order_counts()` in `hackathon/sql/25_app_roles.sql`:
`order_id < 100000000`.

| Tenant | Orders | Seed orders |
|---:|---:|---:|
| 1 | 406 | 405 |
| 2 | 201 | 200 |
| 3 | 47 | 47 |
| 4 | 47 | 47 |
| 5 | 62 | 62 |
| 6 | 43 | 43 |
| 7 | 49 | 49 |
| 8 | 46 | 46 |
| 9 | 51 | 51 |
| 10 | 50 | 50 |
| **Total** | **1,002** | **1,000** |

### Bounded HTTP samples (one request each)

All paths below were GET requests to `127.0.0.1:8093`; milliseconds are single
observations, not latency percentiles or a benchmark.

| Route | HTTP | ms |
|---|---:|---:|
| `/api/health` | 200 | 1.9 |
| `/api/tenants/1/summary` | 200 | 20.7 |
| `/api/tenants/1/trends` | 200 | 11.1 |
| `/api/tenants/1/trends?grain=hour` | 200 | 13.7 |
| `/api/tenants/1/top-products` | 200 | 16.9 |
| `/api/tenants/1/breakdown?by=status` | 200 | 5.1 |
| `/api/tenants/1/breakdown?by=category` | 200 | 5.0 |
| `/api/tenants/1/freshness` | 200 | 4.3 |
| `/api/shards` | 200 | 15.5 |
| `/api/engine` | 200 | 20.5 |
| `/api/monitoring` | 200 | 36.9 |
| `/api/limits` | 200 | 4.6 |

## Screenshot evidence

Captured directly from the existing localhost app with Chromium; no mock page or
fabricated numbers. Screens are point-in-time representative demo data.

- `screenshots/landing-desktop.png`
- `screenshots/analytics-desktop.png`
- `screenshots/analytics-mobile.png`
- `screenshots/shards-desktop.png`
- `screenshots/shards-mobile.png`
- `screenshots/engine-desktop.png`
- `screenshots/monitoring-desktop.png`

## Prior recorded experiments — separate provenance

These are checked-in Mac/representative experiments, not newly run on Fedora.

| Evidence | Recorded conditions | Result / interpretation |
|---|---|---|
| `hackathon/integration/results/oltp-A.txt` vs `oltp-B.txt` | Apple M1, PostgreSQL 18.6 / pg_trickle 0.108.3, 100k representative orders, pgbench 4 clients × 20s, exploratory one-run comparison | 2,457.8 → 1,760.5 TPS (**−28.4%**); mean latency 1.627 → 2.272 ms. Same-run samples only; not official G3 qualification. |
| `hackathon/sharding/results/oltp-delta-shard-a.txt` | Mac two-shard stack; pgbench 4 clients × 20s; two reps; dashboard 135–156 req/s; writer 2/s | Shard A means 1,213.8 → 578.4 TPS (**−52.3%**); average latency 3.30 → 6.94 ms. Explicit database-safety regression. One laptop shared API, generator and both DBs, so it is indicative and confounded. |
| `hackathon/integration/results/lag-diff-1s-idle.json` and `hackathon/docs/handoffs/opus.md` | Mac, 100k representative rows, idle scheduled differential run | Insert visible p50 0.94s / max 1.78s; cancel p50 1.52s / max 2.23s. Not sustained-write or Fedora measurements. |
| `hackathon/app/tests/results/live-bonus-20261031T132216Z.txt` | Mac disposable two-shard test stack | Prior live B1/B2/B3 tests and three-table oracle; not current Fedora and not proof of official scale. |

## Project attribution

The core incremental-view engine is the upstream `pg_trickle` PostgreSQL
extension (Apache-2.0, trickle-labs). AgrregateX's project work is the
tenant-aware order schema and stream-table definitions, SQL correctness oracle,
tenant authorization/routing API, dashboard, operator monitoring, and
acceptance/demo tooling. Do not present the upstream Rust DVM as code written by
the AgrregateX team.

No official 1M/10-tenant or 10M/100-tenant scorecard run has been completed.
