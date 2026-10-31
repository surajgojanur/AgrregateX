-- G3 OLTP transaction for shard A tenants {1,3,4} (REPRESENTATIVE store traffic, not the PRD workload).
-- 1 point read + 1 status update + 1 new order per transaction. Inserted ids >= 300,000,000 are removed
-- between arms by g3_ab.py so every arm starts from the same data size.
\set k random(0, 2)
\set t case when :k = 0 then 1 when :k = 1 then 3 else 4 end
\set o random(1, 10000)
\set p random(1, 200)
\set c random(1, 1000)
SELECT status FROM ax.orders WHERE tenant_id = :t AND order_id >= :o ORDER BY order_id LIMIT 1;
UPDATE ax.orders SET status = CASE status WHEN 'paid' THEN 'shipped' ELSE 'paid' END, updated_at = now()
 WHERE tenant_id = :t AND order_id = (SELECT order_id FROM ax.orders WHERE tenant_id = :t AND order_id >= :o AND order_id < 300000000 ORDER BY order_id LIMIT 1);
INSERT INTO ax.orders (tenant_id, order_id, customer_id, product_id, status, quantity, unit_price_cents, created_at)
VALUES (:t, 300000000 + (:client_id::bigint * 10000000) + random(1, 9999999), :c, :p, 'paid', 2, 1999, now()) ON CONFLICT DO NOTHING;
