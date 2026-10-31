# Synthetic scale datasets (PRD 1M/10 and 10M/100, skewed)

REPRESENTATIVE synthetic data, **not** organiser data. `gen_synthetic.sql` builds the official scale shapes
(**1M orders / 10 tenants** and **10M orders / 100 tenants**, skewed) on a disposable database, during first
boot and **before stream tables exist**: no CDC change buffers fill, and stream tables are built once from the
finished source.

## Dataset definition
| Property | Value |
|---|---|
| Orders | `AX_SEED_ORDERS` (ids `1..N`; live writes use `ax.order_id_seq` from 100,000,000) |
| Tenants | `AX_SEED_TENANTS`; Zipf weights `1/t^s`, `AX_SEED_ZIPF_S` = 1.0 |
| Skew, 10 tenants | measured at 1M: tenant 1 = 34.06 %, tenant 10 = 3.41 % (10×) |
| Skew, 100 tenants | expected: tenant 1 ≈ 19.3 %, tenant 100 ≈ 0.19 % (100×) |
| Per tenant | 200 products in 12 categories, 1,000 customers (the same at every scale, so G5 compares volume only) |
| Columns | customer uniform; product skewed (squared uniform); status mix 25 % paid, 37.5 % shipped, 12.5 % each pending/cancelled/refunded; quantity 1–5; unit price 1.00–999.99; `created_at` uniform over 90 days from 2026-08-02 UTC |

Every column of order `n` is a seeded hash of `(n, AX_SEED)`, not a draw from one `random()` stream. So:
- the dataset is identical for any chunk size;
- a resumed load continues exactly where it stopped;
- a shard (`AX_SHARD_TENANTS='{1,3,4}'`) gets exactly the full dataset's rows for its tenants.

**Load method.** Chunks of `AX_SEED_CHUNK` (250k) each commit together with a progress row in `ax_gen.progress`.
- FK and bucket triggers are skipped during the bulk insert (`session_replication_role = replica`).
- The bucket columns are computed with the trigger's own formula.
- The secondary index is rebuilt once; FKs are then checked in one pass, and any orphan fails the load.
- Re-running with the same parameters is a no-op; different parameters are refused (`ax_gen.params`).

## Run
```bash
cd hackathon
# 1M / 10 (G5 baseline)
AX_SEED_ORDERS=1000000 AX_SEED_TENANTS=10 AX_SCALE_DB_PORT=25580 AX_SCALE_API_PORT=8095 \
  docker compose -p ax-scale-1m -f compose.scale.yaml up -d db
# 10M / 100 (main test): resource gate first (free disk >= 15 GiB, swap headroom, demo stack paused)
AX_SEED_ORDERS=10000000 AX_SEED_TENANTS=100 AX_SCALE_DB_PORT=25581 AX_SCALE_API_PORT=8096 \
  docker compose -p ax-scale-10m -f compose.scale.yaml up -d db
docker logs -f ax-scale-10m-db-1 | grep ax_gen        # progress
PGPASSWORD=local-demo-superuser psql -h 127.0.0.1 -p 25581 -U postgres -d aggregatex -f integration/scale/verify_dataset.sql
docker compose -p ax-scale-10m -f compose.scale.yaml up -d api     # dashboard + API on :8096
```
`verify_dataset.sql` (read-only) reports:
- parameters and load time, sizes, and tenant skew;
- time window and status mix;
- stream-table status and row counts;
- an **exact EXCEPT ALL reconciliation** of all three stream tables against the source (must be 0);
- refresh history.

## Measured (Apple M1, 8 GB, Docker VM 3.8 GiB, PG 18.6 + pg_trickle 0.108.3)
| Dataset | Order load | First boot incl. stream tables | DB size | Stream-table rows (day-product / day-category / hour-category) | Reconciliation |
|---|---|---|---|---|---|
| 100k / 10 | 0.8 s | < 30 s | 104 MB | n/a | 0 / 0 / 0 mismatches |
| 1M / 10 | 3.9 s | 26 s | 648 MB | 432,540 / 53,830 / 557,041 | 0 / 0 / 0 mismatches |
| 10M / 100 | **not run yet** | | | | |

Also tested: shard subset identical to the full dataset (md5 of every row of tenants 1, 3, 4, with different
chunk sizes); re-run is a no-op; mismatched parameters are refused; a simulated interrupted load resumes to an
identical md5.
