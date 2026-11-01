-- Pick REAL existing orders from the 10M dataset for the cases that modify existing rows.
-- All picks lie in the checked window [2026-09-01, 2026-09-06), so the per-case scoped oracle sees them.
CREATE TABLE IF NOT EXISTS g4r.pick AS
SELECT k, order_id FROM (
  SELECT row_number() OVER (ORDER BY order_id) AS rn, order_id
    FROM ax.orders WHERE tenant_id = 1 AND created_at >= '2026-09-01' AND created_at < '2026-09-06'
   ORDER BY order_id LIMIT 9) x
JOIN (VALUES (1,'o2'),(2,'o7'),(3,'o12'),(4,'o17'),(5,'o22'),(6,'o27'),(7,'o32'),(8,'o37'),(9,'o42')) v(rn, k) USING (rn)
UNION ALL
SELECT 't2', min(order_id) FROM ax.orders WHERE tenant_id = 2 AND created_at >= '2026-09-01' AND created_at < '2026-09-06';
