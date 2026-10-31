-- Representative OLTP transaction (NOT the PRD G-3 workload; Codex owns that).
-- 1 PK read + 1 status update + 1 new order, one commit.
\set t random(1, 10)
\set o random(1, 100000)
\set p random(1, 200)
\set c random(1, 1000)
SELECT status, quantity FROM ax.orders WHERE tenant_id = :t AND order_id = :o;
UPDATE ax.orders SET status = CASE status WHEN 'paid' THEN 'shipped' ELSE 'paid' END, updated_at = now()
 WHERE tenant_id = :t AND order_id = (SELECT order_id FROM ax.orders WHERE tenant_id = :t AND order_id >= :o ORDER BY order_id LIMIT 1);
INSERT INTO ax.orders (tenant_id, order_id, customer_id, product_id, status, quantity, unit_price_cents, created_at)
VALUES (:t, 1000000 + (:client_id::bigint * 100000000) + :o * 10 + random(0, 9), :c, :p, 'paid', 2, 1999, now() - random(0, 86400) * interval '1 second')
ON CONFLICT DO NOTHING;
