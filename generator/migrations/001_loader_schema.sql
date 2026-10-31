-- AgrregateX loader bookkeeping (Phase 01A). Loader-owned; does NOT change the
-- frozen public schema (orders, rollups, API grants). Idempotent: safe to re-run.
-- The API role has no privileges on schema `loader`; staged rows are never
-- visible to tenant queries.
CREATE SCHEMA IF NOT EXISTS loader;
REVOKE ALL ON SCHEMA loader FROM PUBLIC;

CREATE TABLE IF NOT EXISTS loader.schema_version(
 version int PRIMARY KEY,
 applied_at timestamptz NOT NULL DEFAULT now()
);

-- One row per dataset load. run_id is a deterministic hash of the spec, so
-- re-planning the same spec resumes the same run instead of creating a twin.
CREATE TABLE IF NOT EXISTS loader.runs(
 run_id text PRIMARY KEY,
 spec jsonb NOT NULL,
 state text NOT NULL CHECK (state IN ('planned','staging','staged','verified','active','aborted')),
 first_ordinal bigint NOT NULL,
 last_ordinal bigint NOT NULL,
 batch_size int NOT NULL CHECK (batch_size > 0),
 total_batches int NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 activated_at timestamptz,
 verification jsonb,
 activation jsonb
);
-- At most one unfinished run: the staging tables belong to it.
CREATE UNIQUE INDEX IF NOT EXISTS runs_one_open ON loader.runs((true))
 WHERE state NOT IN ('active','aborted');

-- Durable checkpoints. A row exists iff the batch's staged rows and rollup
-- deltas committed in the same transaction.
CREATE TABLE IF NOT EXISTS loader.batches(
 run_id text NOT NULL REFERENCES loader.runs ON DELETE CASCADE,
 batch_no int NOT NULL,
 first_ordinal bigint NOT NULL,
 last_ordinal bigint NOT NULL,
 row_count int NOT NULL,
 fingerprint numeric NOT NULL,
 units bigint NOT NULL,
 cents bigint NOT NULL,
 daily_groups int NOT NULL,
 hourly_groups int NOT NULL,
 elapsed_ms numeric NOT NULL,
 wal_bytes bigint,
 committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(run_id,batch_no),
 CHECK (last_ordinal >= first_ordinal AND row_count = last_ordinal-first_ordinal+1)
);

-- Staged source rows. Deterministic identity: ordinal i becomes orders.id = -i
-- (bulk IDs negative, API IDs positive, as in Phase 00).
CREATE TABLE IF NOT EXISTS loader.stage_orders(
 ordinal bigint PRIMARY KEY CHECK (ordinal > 0),
 tenant_id int NOT NULL,
 customer_id int NOT NULL,
 product_id int NOT NULL,
 category_id int NOT NULL,
 ordered_at timestamptz NOT NULL,
 status text NOT NULL,
 quantity int NOT NULL,
 unit_price_cents bigint NOT NULL
);

-- Accumulated rollup deltas of all staged rows (same shape/semantics as the
-- public rollups). Merged additively into public rollups at activation.
CREATE TABLE IF NOT EXISTS loader.delta_daily(
 tenant_id int NOT NULL, bucket timestamptz NOT NULL, product_id int NOT NULL, category_id int NOT NULL,
 status text NOT NULL, n bigint NOT NULL, units bigint NOT NULL, cents bigint NOT NULL,
 PRIMARY KEY(tenant_id,bucket,product_id,category_id,status)
);
CREATE TABLE IF NOT EXISTS loader.delta_hourly(
 tenant_id int NOT NULL, bucket timestamptz NOT NULL, category_id int NOT NULL,
 status text NOT NULL, n bigint NOT NULL, units bigint NOT NULL, cents bigint NOT NULL,
 PRIMARY KEY(tenant_id,bucket,category_id,status)
);

INSERT INTO loader.schema_version(version) VALUES (1) ON CONFLICT DO NOTHING;
