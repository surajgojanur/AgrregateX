# Opus P1 engine spike — reproduce

This is a disposable, isolated database: PG 18.6 + pg_trickle 0.108.3, on `127.0.0.1:25540`, with PGDATA on tmpfs.
**Test-only:** `spike_lib.sql`, `ab_run.sh`, `lag_probe.py` and `pgbench_oltp.sql` must never run against a judged database.

```bash
cd hackathon
docker compose -f integration/spike-compose.yaml up -d --wait
export PGPASSWORD=spike-only-not-secret PGHOST=127.0.0.1 PGPORT=25540 PGUSER=postgres PGDATABASE=tenant_gen
psql -c "create database tenant_gen" -d tenant_shared
psql -v ON_ERROR_STOP=1 -c "create extension if not exists pg_trickle" \
     -f sql/00_schema.sql -f integration/seed.sql -f sql/05_bucket_columns.sql   # seed: -v orders=100000 -v tenants=10

# Correctness + effective mode (recreates the stream tables): MODE SCHED CDC N_MUTATIONS DIM_CHURN LABEL
integration/ab_run.sh DIFFERENTIAL 1s trigger 5000 false my-run     # writes results/ab-my-run.txt
# NOTE: wait_fresh() only proves "a refresh started after T". Bursts drain over several refreshes,
# so if the oracle is non-zero, re-run `select * from ax.oracle_mismatches()` after the backlog
# drains before calling it a mismatch.

# Security (apply AFTER the stream tables exist, then reinitialize; see handoff F7)
psql -f sql/20_security.sql
psql -c "select pgtrickle.reinitialize_stream_table(n) from unnest(array['ax.st_day_product_status','ax.st_day_category_status','ax.st_hour_category_status']) n"
psql -f integration/rls_test.sql

# Commit->visible lag (client-side autocommit polling)
python3 -I integration/lag_probe.py my-lag 15

# Indicative OLTP overhead (NOT the PRD G-3 harness)
pgbench -n -c 4 -j 2 -T 20 -f integration/pgbench_oltp.sql tenant_gen

docker compose -f integration/spike-compose.yaml down    # destroys all data
```

`results/` holds the raw outputs quoted in `docs/handoffs/opus.md`. They are n=1 laptop runs, indicative only.
`results/ab-diff-1s-trigger-nochurn.txt` and `ab-gen-diff-1s-trigger-nochurn.txt` record the two **failed** variants, kept as evidence:
the subquery form (slow; it timed out) and the GENERATED columns form (ERROR).
