-- AgrregateX synthetic dataset generator for the PRD scale tests (1M/10 and 10M/100, skewed).
-- REPRESENTATIVE synthetic data, NOT organiser data.
--
-- Properties
--   * Deterministic and order-independent: every column of order n is a hash of (n, seed),
--     not a draw from one global random() stream. Any chunk, resume point or tenant subset
--     (a shard) regenerates exactly the same rows.
--   * Skewed tenants: Zipf weights w(t) = 1 / t^zipf_s (default s = 1.0).
--     10M/100 -> tenant 1 ~ 19.3 %, tenant 100 ~ 0.19 %; 1M/10 -> tenant 1 ~ 34 %, tenant 10 ~ 3.4 %.
--   * Same per-tenant key cardinality at every scale (200 products in 12 categories,
--     1,000 customers), so 1M vs 10M (G5) changes only the volume and the tenant count.
--   * Chunked and resumable: each chunk commits together with its progress row
--     (ax_gen.progress). Re-running continues after the last committed chunk.
--
-- Load order (must run BEFORE stream tables exist; init.sh does this):
--   00_schema.sql -> 05_bucket_columns.sql (on the empty table) -> THIS -> 10_stream_tables.sql ...
-- Bucket columns (utc_day, utc_hour, line_cents) are computed here with the same formula as the
-- ax.orders_derive_buckets trigger. FK and bucket triggers are skipped during the bulk load
-- (session_replication_role = replica, superuser only) and FKs are then checked in one pass.
--
-- psql vars: :orders (default 1000000), :tenants (default 10), :seed (default 42),
--            :zipf_s (default 1.0), :chunk (default 250000),
--            :shard_tenants  optional int[] literal ('{1,3,4}') to keep only one shard's tenants.
\set ON_ERROR_STOP 1
\if :{?orders}
\else
  \set orders 1000000
\endif
\if :{?tenants}
\else
  \set tenants 10
\endif
\if :{?seed}
\else
  \set seed 42
\endif
\if :{?zipf_s}
\else
  \set zipf_s 1.0
\endif
\if :{?chunk}
\else
  \set chunk 250000
\endif
\if :{?shard_tenants}
\else
  \set shard_tenants ''
\endif

CREATE SCHEMA IF NOT EXISTS ax_gen;
REVOKE ALL ON SCHEMA ax_gen FROM PUBLIC;

CREATE TABLE IF NOT EXISTS ax_gen.params (
    id integer PRIMARY KEY CHECK (id = 1),
    orders bigint NOT NULL, tenants integer NOT NULL, seed bigint NOT NULL,
    zipf_s float8 NOT NULL, shard_tenants integer[], started_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS ax_gen.progress (
    lo bigint PRIMARY KEY, hi bigint NOT NULL, rows_inserted bigint NOT NULL,
    committed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

-- A resumed run must use the same parameters, otherwise the dataset would be a mix.
INSERT INTO ax_gen.params (id, orders, tenants, seed, zipf_s, shard_tenants)
VALUES (1, :orders, :tenants, :seed, :zipf_s, NULLIF(:'shard_tenants', '')::int[])
ON CONFLICT (id) DO NOTHING;
SELECT (p.orders, p.tenants, p.seed, p.zipf_s) IS NOT DISTINCT FROM
       (:orders::bigint, :tenants::int, :seed::bigint, :zipf_s::float8)
   AND p.shard_tenants IS NOT DISTINCT FROM NULLIF(:'shard_tenants', '')::int[] AS params_ok
  FROM ax_gen.params p \gset
\if :params_ok
\else
  DO $$ BEGIN RAISE EXCEPTION 'ax_gen: parameters differ from the run in progress (see ax_gen.params); refusing to mix datasets'; END $$;
\endif

-- Uniform [0,1) from a 53-bit slice of a seeded 64-bit hash of (n, stream k).
CREATE OR REPLACE FUNCTION ax_gen.u(n bigint, k bigint) RETURNS float8
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS
$$ SELECT ((hashint8extended(n, k) >> 11) & 9007199254740991)::float8 / 9007199254740992.0 $$;

-- Lower CDF bound per tenant: thresholds[t] = P(tenant < t); width_bucket picks the tenant.
CREATE OR REPLACE FUNCTION ax_gen.tenant_thresholds(p_tenants int, p_s float8) RETURNS float8[]
LANGUAGE sql IMMUTABLE AS $$
    SELECT array_agg(x.below / x.total ORDER BY x.t)
    FROM (SELECT t,
                 coalesce(sum(w) OVER (ORDER BY t ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0) AS below,
                 sum(w) OVER () AS total
          FROM (SELECT t, 1.0 / power(t, p_s) AS w FROM generate_series(1, p_tenants) t) w) x
$$;

-- Dimensions (idempotent).
INSERT INTO ax.tenants
SELECT t, 'tenant-' || t FROM generate_series(1, :tenants) t
WHERE NULLIF(:'shard_tenants', '') IS NULL OR t = ANY (NULLIF(:'shard_tenants', '')::int[])
ON CONFLICT DO NOTHING;
INSERT INTO ax.products
SELECT t.tenant_id, p, 1 + (p % 12), 'product-' || t.tenant_id || '-' || p
FROM ax.tenants t, generate_series(1, 200) p
ON CONFLICT DO NOTHING;
INSERT INTO ax.customers
SELECT t.tenant_id, c, 'customer-' || t.tenant_id || '-' || c
FROM ax.tenants t, generate_series(1, 1000) c
ON CONFLICT DO NOTHING;

CREATE OR REPLACE PROCEDURE ax_gen.load_orders(p_chunk bigint)
LANGUAGE plpgsql AS $p$
DECLARE
    p   ax_gen.params;
    thr float8[];
    v_lo  bigint;
    v_hi  bigint;
    v_rows bigint;
    t0  timestamptz;
    k   bigint;
BEGIN
    SELECT * INTO p FROM ax_gen.params;
    thr := ax_gen.tenant_thresholds(p.tenants, p.zipf_s);
    k   := p.seed * 16;                      -- 16 independent hash streams per seed
    SELECT coalesce(max(g.hi), 0) + 1 INTO v_lo FROM ax_gen.progress g;
    IF v_lo > 1 THEN RAISE NOTICE 'ax_gen: resuming at order %', v_lo; END IF;
    PERFORM set_config('session_replication_role', 'replica', false);   -- skip FK + bucket triggers
    WHILE v_lo <= p.orders LOOP
        v_hi := least(v_lo + p_chunk - 1, p.orders);
        t0 := clock_timestamp();
        INSERT INTO ax.orders (tenant_id, order_id, customer_id, product_id, status, quantity,
                               unit_price_cents, created_at, updated_at, utc_day, utc_hour, line_cents)
        SELECT r.tid, r.n, r.cid, r.pid, r.st, r.q, r.price, r.ts, r.ts,
               date_trunc('day',  r.ts AT TIME ZONE 'UTC'),
               date_trunc('hour', r.ts AT TIME ZONE 'UTC'),
               r.q::bigint * r.price
        FROM (
            SELECT s.n,
                   width_bucket(ax_gen.u(s.n, k + 1), thr)                         AS tid,
                   1 + floor(ax_gen.u(s.n, k + 2) * 1000)::int                     AS cid,
                   1 + floor(power(ax_gen.u(s.n, k + 3), 2) * 200)::int            AS pid,
                   (ARRAY['pending','paid','paid','shipped','shipped','shipped','cancelled','refunded'])
                       [1 + floor(ax_gen.u(s.n, k + 4) * 8)::int]                  AS st,
                   1 + floor(ax_gen.u(s.n, k + 5) * 5)::int                        AS q,
                   100 + floor(ax_gen.u(s.n, k + 6) * 99900)::bigint               AS price,
                   timestamptz '2026-08-02 00:00:00+00'
                       + ax_gen.u(s.n, k + 7) * interval '90 days'                 AS ts
            FROM generate_series(v_lo, v_hi) s(n)
        ) r
        WHERE p.shard_tenants IS NULL OR r.tid = ANY (p.shard_tenants);
        GET DIAGNOSTICS v_rows = ROW_COUNT;
        INSERT INTO ax_gen.progress (lo, hi, rows_inserted) VALUES (v_lo, v_hi, v_rows);
        COMMIT;
        RAISE NOTICE 'ax_gen: orders % .. % of % (% rows, % s)', v_lo, v_hi, p.orders, v_rows,
            round(extract(epoch FROM clock_timestamp() - t0)::numeric, 1);
        v_lo := v_hi + 1;
    END LOOP;
    PERFORM set_config('session_replication_role', 'origin', false);
END $p$;

-- Bulk load faster without the secondary index; it is rebuilt once afterwards.
DROP INDEX IF EXISTS ax.orders_tenant_created_idx;
CALL ax_gen.load_orders(:chunk);
CREATE INDEX IF NOT EXISTS orders_tenant_created_idx ON ax.orders (tenant_id, created_at);

-- FKs were not checked row by row during the load: check them once, fail loudly.
DO $fk$
DECLARE bad_p bigint; bad_c bigint;
BEGIN
    SELECT count(*) INTO bad_p FROM ax.orders o
     WHERE NOT EXISTS (SELECT 1 FROM ax.products p WHERE p.tenant_id = o.tenant_id AND p.product_id = o.product_id);
    SELECT count(*) INTO bad_c FROM ax.orders o
     WHERE NOT EXISTS (SELECT 1 FROM ax.customers c WHERE c.tenant_id = o.tenant_id AND c.customer_id = o.customer_id);
    IF bad_p + bad_c > 0 THEN
        RAISE EXCEPTION 'ax_gen: % orders without product, % without customer', bad_p, bad_c;
    END IF;
END $fk$;

VACUUM (ANALYZE) ax.tenants, ax.products, ax.customers, ax.orders;
SELECT p.orders AS generated_ids, p.tenants, p.seed, p.zipf_s, p.shard_tenants,
       (SELECT count(*) FROM ax.orders) AS orders_rows,
       round(extract(epoch FROM max(g.committed_at) - p.started_at)::numeric, 1) AS load_s
FROM ax_gen.params p, ax_gen.progress g GROUP BY p.orders, p.tenants, p.seed, p.zipf_s, p.shard_tenants, p.started_at;
