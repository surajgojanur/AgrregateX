# 10M / 100 tenants: load, storage, correctness, HTTP latency and growth vs 1M (#31, #42)

**Scope.** This is REPRESENTATIVE synthetic data (`gen_synthetic.sql`, seed 42, Zipf s = 1.0), not organiser data.
- **Approval:** the human operator approved the 10M run on #31 / #42 before launch, with a passing preflight (17 GiB free disk, nothing else running).
- **Stack:** single-DB scale stack `ax-scale-10m` (`compose.scale.yaml`; DB :25581, API :8096, auth off for the load client). PostgreSQL 18.6 + pg_trickle 0.108.3, image `sha256:94344bb9…`.
- **Host:** Apple M1, 8 GB, Docker VM 3.8 GiB; the client, API and database share it.

## Load and storage
| Fact | Value |
|---|---|
| Orders | **10,000,000** (ids 1 to 10,000,000, all distinct), 90 days 2026-08-02 → 2026-10-30 |
| Tenants | **100**; largest t1 = **1,930,247**, median t51 = 37,901, smallest t100 = **19,471** (about 99×) |
| Generator record (`ax_gen.params` / `progress`) | 10,000,000 orders, 100 tenants, seed 42; **40 chunks, 40.2 s** order load |
| Where it lives | PostgreSQL table `ax.orders` in Docker volume **`ax-scale-10m_scaledata`**; database **5.7 GB** (orders 1.1 GB + indexes 0.6 GB) |
| Stream tables | `st_day_product_status` 3,434,989 rows (1.2 GB); `st_day_category_status` 529,273 (187 MB); `st_hour_category_status` 4,349,680 (1.5 GB); all ACTIVE / DIFFERENTIAL |
| Initial build (from logs) | first boot finished all steps (`initialised`). The init server then exceeded `pg_ctl`'s 60 s shutdown wait while checkpointing ~4 GB of WAL, so the container exited (code 1, not OOM). On restart, crash recovery replayed WAL in 187 s; nothing was lost. The final scheduled rebuilds took 149.8 s (product), 17.3 s (day/category) and 435 s (hour/category) under memory pressure |

## Correctness
| Check | Result | File |
|---|---|---|
| Exact stream tables vs raw source, **all 10M rows** (`oracle_lowmem.sql`: sort/merge, one table at a time) | **0/0 · 0/0 · 0/0** in 208 s, peak ~1.0 GiB container memory | `10m-100t-proof/oracle-lowmem*.txt` |
| Dashboard API `/summary` (full range) vs direct count, **all 100 tenants** | **100 / 100 match; 10,000,000 = 10,000,000** (p50 45 ms; max 987 ms = largest tenant's first, cold call) | `10m-100t-proof/api-vs-db-100-tenants.json` |

**Incident during verification:** the first oracle attempt (the original all-in-one hashed `ax.oracle_mismatches()` with `work_mem=128MB`) was **OOM-killed** inside the 2 GiB container. Postgres crash-recovered in about 3 minutes; committed data was intact (count and stream-table state re-checked). `oracle_lowmem.sql` is the memory-safe replacement used above.

## G1 query speed and G5 growth (`http_latency.py`, identical method to 1M: 72 scenarios × 50 sequential requests after warm-up, no concurrent writes)
| Metric | 10M / 100 | PRD |
|---|---|---|
| Requests / errors | 3,600 / **0** | n/a |
| Scenarios with p95 < 200 ms | **71 / 72**; worst p95 **240.6 ms** (top-products, largest tenant, 90 d) | Great < 200 ms |
| Scenarios with p95 < 1 s | **72 / 72**; worst p99 457 ms | Good < 1 s |
| **Growth p95 10M ÷ 1M**, 72 matched scenarios (same endpoint, tenant role, window) | **median 1.18×**; 66 / 72 < 2×; 71 / 72 < 5×; worst **5.18×** (the same top-products / largest / 90 d case: 46 → 241 ms) | Great < 2×, Good < 5× |

**Reading:**
- G1 is Great in 71 of 72 scenarios and Good in all 72.
- G5 median growth is Great, with one Good-threshold miss.
- Caveat: tenant roles are matched by size **rank**, not identical tenants. The largest tenant grew 5.7× (340,560 → 1,930,247 orders), which bounds the worst ratio. Raw data: `10m-100t-http/`, `10m-100t-http/growth_vs_1m.json`.

## Not covered
- Freshness (G2) and database safety (G3) at 10M under write load. The FULL-refresh mitigation for the #50 / #54 defect costs 149.8 s per product-rollup rebuild at 10M (see the #54 design).
- Live-update correctness at 10M depends on the #54 fix.
- Organiser data and schema; the two-shard topology at 10M.

## Reproduce
```bash
cd hackathon
AX_SEED_ORDERS=10000000 AX_SEED_TENANTS=100 AX_SCALE_DB_PORT=25581 AX_SCALE_API_PORT=8096 \
  docker compose -p ax-scale-10m -f compose.scale.yaml up -d db        # then: ... up -d api
PGPASSWORD=$AX_DB_SUPERUSER_PASSWORD psql -h 127.0.0.1 -p 25581 -U postgres -d aggregatex \
  -f integration/scale/oracle_lowmem.sql
cd integration/scale && python3 -I http_latency.py --api http://127.0.0.1:8096 \
  --dsn "host=127.0.0.1 port=25581 dbname=aggregatex user=postgres password=$AX_DB_SUPERUSER_PASSWORD" \
  --n 50 --out results/10m-100t-http
```
