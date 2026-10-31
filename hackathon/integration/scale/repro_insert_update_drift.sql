-- REPRO (pg_trickle 0.108.3, DIFFERENTIAL): an INSERT and a later UPDATE of the same source row that are
-- consumed in ONE refresh delta leave the single-table aggregate ax.st_day_product_status with the
-- INSERTED row image (status 'paid'); the UPDATE (-> 'cancelled') is lost. The joined aggregates
-- (st_day_category_status, st_hour_category_status) are correct for the same rows.
-- Observed 5/5 on the 1M/10 scale stack (refresh ~3 s, so a 0.3 s gap always shares a delta), and
-- naturally under the demo writer (33 'paid' over-counts on 2026-10-31) and after scheduler stalls
-- on the two-shard demo (#42 P0-2).
-- DISPOSABLE DATABASE ONLY: inserts 5 orders (tenant 9, day 2026-11-20, products 191..195, ids 291000001..5).
-- usage: psql -h 127.0.0.1 -p <scale db port> -U postgres -d aggregatex -f repro_insert_update_drift.sql
\set ON_ERROR_STOP 1
DO $$ BEGIN FOR n IN 1..5 LOOP
  INSERT INTO ax.orders (tenant_id, order_id, customer_id, product_id, status, quantity, unit_price_cents, created_at)
  VALUES (9, 291000000 + n, 1, 190 + n, 'paid', 1, 1000, '2026-11-20 12:00:00+00');
END LOOP; END $$;
SELECT pg_sleep(0.3);
UPDATE ax.orders SET status = 'cancelled', updated_at = now() WHERE order_id BETWEEN 291000001 AND 291000005;
SELECT pg_sleep(25);   -- several refresh cycles
\echo 'EXPECTED: ST rows = SRC rows (5 x cancelled). BUG: ST keeps 5 x paid.'
SELECT 'ST' AS side, product_id, status, order_count FROM ax.st_day_product_status
 WHERE tenant_id = 9 AND utc_day = '2026-11-20' AND product_id BETWEEN 191 AND 195
UNION ALL
SELECT 'SRC', product_id, status, count(*) FROM ax.orders
 WHERE tenant_id = 9 AND utc_day = '2026-11-20' AND product_id BETWEEN 191 AND 195 GROUP BY 2, 3
ORDER BY 2, 1, 3;
SELECT stream_table, missing_in_st, extra_in_st FROM ax.oracle_mismatches();
