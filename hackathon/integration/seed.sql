-- REPRESENTATIVE deterministic skewed seed (NOT organizer data).
-- psql vars: :tenants (default 10), :orders (default 100000), :seed (default 0.42)
-- Skew: tenant 1 ≈ 40 %, tenant 2 ≈ 20 %, the rest share the remaining 40 %.
\if :{?tenants}
\else
  \set tenants 10
\endif
\if :{?orders}
\else
  \set orders 100000
\endif
\if :{?seed}
\else
  \set seed 0.42
\endif
SELECT setseed(:seed);

INSERT INTO ax.tenants
SELECT t, 'tenant-' || t FROM generate_series(1, :tenants) t;

INSERT INTO ax.products
SELECT t, p, 1 + (p % 12), 'product-' || t || '-' || p
FROM generate_series(1, :tenants) t, generate_series(1, 200) p;

INSERT INTO ax.customers
SELECT t, c, 'customer-' || t || '-' || c
FROM generate_series(1, :tenants) t, generate_series(1, 1000) c;

INSERT INTO ax.orders (tenant_id, order_id, customer_id, product_id, status,
                       quantity, unit_price_cents, created_at, updated_at)
SELECT tid,
       n,
       1 + floor(random() * 1000)::int,
       -- mild product popularity skew (squared uniform)
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
                ELSE 3 + floor((r - 0.60) / 0.40 * (:tenants - 2))::int
           END AS tid
    FROM (SELECT n, random() AS r FROM generate_series(1, :orders) n) s
) g;

ANALYZE ax.tenants, ax.products, ax.customers, ax.orders;
