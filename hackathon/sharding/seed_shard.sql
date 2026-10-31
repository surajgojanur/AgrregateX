-- Shard seed: the SAME deterministic global dataset as integration/seed.sql (REPRESENTATIVE,
-- not organizer data), filtered to this shard's tenants. Every shard draws the identical random
-- sequence, so shards are disjoint by tenant and their union is exactly the global seed:
-- order_id 1..:orders appears on exactly one shard.
-- psql vars: :tenants  int[] literal of tenants owned by this shard, e.g. '{1,3,4}'
--            :orders   GLOBAL order count (default 10000), :all_tenants (default 10), :seed (0.42)
\if :{?orders}
\else
  \set orders 10000
\endif
\if :{?all_tenants}
\else
  \set all_tenants 10
\endif
\if :{?seed}
\else
  \set seed 0.42
\endif
SELECT setseed(:seed);

INSERT INTO ax.tenants
SELECT t, 'tenant-' || t FROM generate_series(1, :all_tenants) t
WHERE t = ANY (:'tenants'::int[]);

INSERT INTO ax.products
SELECT t, p, 1 + (p % 12), 'product-' || t || '-' || p
FROM generate_series(1, :all_tenants) t, generate_series(1, 200) p
WHERE t = ANY (:'tenants'::int[]);

INSERT INTO ax.customers
SELECT t, c, 'customer-' || t || '-' || c
FROM generate_series(1, :all_tenants) t, generate_series(1, 1000) c
WHERE t = ANY (:'tenants'::int[]);

-- Generate ALL global rows (same random() consumption on every shard), keep only ours.
INSERT INTO ax.orders (tenant_id, order_id, customer_id, product_id, status,
                       quantity, unit_price_cents, created_at, updated_at)
SELECT * FROM (
    SELECT tid, n,
           1 + floor(random() * 1000)::int,
           1 + floor(power(random(), 2) * 200)::int,
           (ARRAY['pending','paid','paid','shipped','shipped','shipped','cancelled','refunded'])
               [1 + floor(random() * 8)::int],
           1 + floor(random() * 5)::int,
           100 + floor(random() * 99900)::bigint,
           timestamptz '2026-08-02 00:00:00+00' + random() * interval '90 days',
           now()
    FROM (
        SELECT n,
               CASE WHEN r < 0.40 THEN 1
                    WHEN r < 0.60 THEN 2
                    ELSE 3 + floor((r - 0.60) / 0.40 * (:all_tenants - 2))::int
               END AS tid
        FROM (SELECT n, random() AS r FROM generate_series(1, :orders) n) s
    ) g
    ORDER BY n            -- materialise every row before filtering
) all_rows (tid, n, c, p, st, q, u, ts, up)
WHERE tid = ANY (:'tenants'::int[]);

ANALYZE ax.tenants, ax.products, ax.customers, ax.orders;
