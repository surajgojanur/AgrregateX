# 1M / 10 tenants: end-to-end HTTP latency, freshness and correctness (#42 P1-4, for #31)

**Scope.** This is representative synthetic data (`gen_synthetic.sql`, seed 42, Zipf s = 1.0), not organiser data. It ran on the single-DB scale stack `ax-scale-1m` (`compose.scale.yaml`; DB :25580, API :8095, auth off for the load client). Engine: PG 18.6 + pg_trickle 0.108.3 (image `sha256:94344bb9…`). Host: an Apple M1 with 8 GB, shared by the client, API and database. The user's demo stack was paused during the run.

| Dataset fact | Value |
|---|---|
| Orders | 1,000,000 (ids 1..1M) |
| Tenant roles | largest **t1 = 340,560**, median **t6 = 56,965**, smallest **t10 = 34,091** orders |
| Window | 2026-08-02 .. 2026-10-31 UTC (90 days) |
| Stream tables | 3, ACTIVE; exact oracle **0/0/0** at start |

## G1 query speed: HTTP p95 (ms), 50 sequential requests per scenario after 3 warm-up requests, no concurrent writes
Each cell is **largest / median / smallest tenant**. `trends` uses hourly grain up to 7 days and daily grain beyond.

| Endpoint | 1 h | 1 d | 7 d | 30 d | 90 d | Unaligned 7 d (partial edges) |
|---|---|---|---|---|---|---|
| summary | 4.3 / 2.2 / 2.2 | 4.4 / 2.5 / 2.5 | 10.4 / 4.3 / 6.8 | 41.4 / 13.0 / 7.4 | **60.8** / 30.8 / 18.7 | 11.4 / 5.5 / 6.5 |
| trends | 4.7 / 2.6 / 2.1 | 11.5 / 2.7 / 2.5 | 12.1 / 7.4 / 7.5 | 6.6 / 3.3 / 3.1 | 7.3 / 5.9 / 8.1 | 14.8 / 7.2 / 7.6 |
| top-products | 3.2 / 2.3 / 2.4 | 5.3 / 2.9 / 3.2 | 8.3 / 5.9 / 3.7 | 19.9 / 12.3 / 7.2 | 46.4 / 25.2 / 21.1 | 15.5 / 6.9 / 5.3 |
| breakdown | 4.9 / 2.4 / 2.5 | 3.6 / 2.7 / 5.5 | 10.5 / 4.0 / 4.0 | 26.0 / 10.6 / 8.4 | 60.4 / 26.2 / 19.0 | 10.1 / 4.1 / 4.3 |

- **Idle (`1m-10t-http/`):** 3,600 requests, **0 errors**. Worst p95 **60.8 ms**, worst p99 **173.5 ms**, worst max 173.5 ms. **72 of 72 scenarios have p95 < 200 ms.**
- **With the demo writer at 5 changes/s (`1m-10t-http-writer5/`, n = 20):** 1,440 requests, **0 errors**. Worst p95 **81.7 ms**, worst max 86.4 ms. 72 of 72 have p95 < 200 ms.
- **Reading:** this meets the PRD G1 **Great** threshold (< 200 ms) at 1M for this data, host and concurrency 1. Latency grows with window length for the stream-table range scans (summary, top-products, breakdown); trends stays below 15 ms.
- **Not measured:** concurrent multi-client load, and 10M (G5 needs matched 1M and 10M runs on the same host).

## Correctness
- **API vs raw SQL** (`app/tests/api_oracle.py`, 15 windows): **225 checks, 0 mismatches** (`1m-10t-http/api_oracle.txt`).
- **Stream tables vs source, exact `EXCEPT ALL`:** 0/0/0 before the writer ran.
- **CORRECTNESS FAIL after the writer (5 changes/s) ran for a few minutes.** Once quiesced and drained, `st_day_product_status` showed **16 missing / 31 extra** groups, and the two joined stream tables were 0/0. Every wrong group is `paid` on the current day; the stream table over-counts `paid` by **33 orders** (`1m-10t-http-writer5/drift-analysis.txt`). The writer cancels or ships *recent* paid orders, so a row's INSERT and its UPDATE often land in the same delta.
- **Deterministic repro, 5 of 5** (`repro_insert_update_drift.sql`, `1m-10t-http-writer5/drift-repro.txt`):
  - **Steps:** INSERT `paid`, UPDATE to `cancelled` 0.3 s later in a separate commit; both changes are consumed by one DIFFERENTIAL refresh (`delete_insert`, delta 5).
  - **Result:** `st_day_product_status` keeps the **inserted** image (`paid` = 1), and `cancelled` never appears.
  - **Joined tables:** `st_day_category_status` and `st_hour_category_status` are correct (`cancelled` = 1) for the same rows.
  - **Scope:** this is the same defect as the #42 P0-2 two-shard drift.
- **Mitigation tested** (reversible config, no Rust; `drift-repro-full-mode.txt`):
  - `alter_stream_table('ax.st_day_product_status', refresh_mode => 'FULL')` makes the repro correct (5 × `cancelled`), repairs the accumulated drift, and the whole-table oracle returns to **0/0/0**.
  - **Cost:** a FULL refresh of that table takes **5.8 s** at 1M (DIFFERENTIAL takes 3.3 s). The table was reverted to DIFFERENTIAL afterwards.
- **Remediation for existing drift:** a FULL refresh or reinitialisation (B-2 `python -m axapi.rebuild`).
- **Root cause:** upstream (net-change handling for the single-table aggregate). **Any Rust fix needs human approval.**

## G2 freshness at 1M (writer 5 changes/s)
| Measure | Result |
|---|---|
| DIFFERENTIAL refresh duration (90 s window) | `st_day_category_status` avg 1.6 s · `st_day_product_status` avg 3.3 s (max 4.4) · `st_hour_category_status` avg **5.0 s** (max 6.5), each against a **1 s** schedule |
| Pending CDC rows (70 s timeline, every 10 s) | 269–488: bounded, not growing |
| **Commit→visible** (`/live-write`; insert and cancel; tenants 1, 2, 4, 6, 10; data-based rule: all 3 stream tables equal source) | **8 probes, 0 timeouts; median 18.7 s, max 24.0 s** |

- **Reading:** within the PRD **Great** threshold (< 30 s), but with a thin margin and n = 8.
- **Refresh cost:** each DIFFERENTIAL refresh at 1M takes seconds, not milliseconds. This is consistent with P1 (the null-safe group-key join forces a nested loop that grows with stream-table size).
- **At 10k / 200 TPS** (G3 run, PR #46), freshness **fails**: 18 of 20 probes took > 30 s.
- **Never** read refresh-age metadata as commit→visible.

## Reproduce
```bash
cd hackathon
AX_SEED_ORDERS=1000000 AX_SEED_TENANTS=10 AX_SCALE_DB_PORT=25580 AX_SCALE_API_PORT=8095 \
  docker compose -p ax-scale-1m -f compose.scale.yaml up -d --build --wait db api
cd integration/scale
python3 -I http_latency.py --api http://127.0.0.1:8095 \
  --dsn "host=127.0.0.1 port=25580 dbname=aggregatex user=postgres password=$AX_DB_SUPERUSER_PASSWORD" \
  --n 50 --out results/1m-10t-http
```
