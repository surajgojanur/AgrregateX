-- GENERATED from ../cases.sql for the 10M dataset (ids remapped; see pick.sql). #54 regression matrix. Each case commits its statements as SEPARATE transactions, then check.sql
-- refreshes once, so the whole history lands in ONE refresh window (scheduler disabled).
\set ON_ERROR_STOP on
\set case A0_baseline
\i :here/check10m.sql

\set case A1_insert
INSERT INTO ax.orders VALUES (1, 20000001, 1, 1, 'paid', 2, 1500, '2026-09-03 10:00+00');
\i :here/check10m.sql

\set case A2_insert_then_cancel_same_window
INSERT INTO ax.orders VALUES (1, 20000002, 1, 2, 'paid', 1, 1200, '2026-09-03 11:00+00');
UPDATE ax.orders SET status = 'cancelled' WHERE tenant_id = 1 AND order_id = 20000002;
\i :here/check10m.sql

\set case A2x_insert_then_cancel_across_windows
INSERT INTO ax.orders VALUES (1, 20000003, 1, 3, 'paid', 1, 1200, '2026-09-03 12:00+00');
\i :here/check10m.sql
\set case A2x_insert_then_cancel_across_windows_b
UPDATE ax.orders SET status = 'cancelled' WHERE tenant_id = 1 AND order_id = 20000003;
\i :here/check10m.sql

\set case A3_update_then_delete_same_window
UPDATE ax.orders SET status = 'shipped' WHERE tenant_id = 1 AND order_id = :o2;
DELETE FROM ax.orders WHERE tenant_id = 1 AND order_id = :o2;
\i :here/check10m.sql

\set case A4_paid_cancelled_refunded
UPDATE ax.orders SET status = 'cancelled' WHERE tenant_id = 1 AND order_id = :o7;
UPDATE ax.orders SET status = 'refunded' WHERE tenant_id = 1 AND order_id = :o7;
\i :here/check10m.sql

\set case A5_delete
DELETE FROM ax.orders WHERE tenant_id = 1 AND order_id = :o12;
\i :here/check10m.sql

\set case A6_insert_then_delete
INSERT INTO ax.orders VALUES (1, 20000006, 1, 4, 'paid', 1, 1000, '2026-09-04 10:00+00');
DELETE FROM ax.orders WHERE tenant_id = 1 AND order_id = 20000006;
\i :here/check10m.sql

\set case A7_quantity_and_price
UPDATE ax.orders SET quantity = quantity + 5, unit_price_cents = unit_price_cents + 333 WHERE tenant_id = 1 AND order_id = :o17;
\i :here/check10m.sql

\set case A8a_product_move
UPDATE ax.orders SET product_id = 23 WHERE tenant_id = 1 AND order_id = :o22;
\i :here/check10m.sql

\set case A8b_category_move_via_products
UPDATE ax.products SET category_id = 9 WHERE tenant_id = 1 AND product_id = 5;
\i :here/check10m.sql

\set case A9_created_at_across_day_and_hour
UPDATE ax.orders SET created_at = created_at + interval '1 day 3 hours' WHERE tenant_id = 1 AND order_id = :o27;
\i :here/check10m.sql

\set case A10_same_group_mixed
INSERT INTO ax.orders VALUES (1, 20000010, 1, 6, 'paid', 1, 1000, '2026-09-05 09:00+00'),
                             (1, 20000011, 1, 6, 'paid', 2, 1000, '2026-09-05 09:30+00'),
                             (1, 20000012, 1, 6, 'paid', 3, 1000, '2026-09-05 09:45+00');
UPDATE ax.orders SET status = 'shipped' WHERE tenant_id = 1 AND order_id = 20000010;
DELETE FROM ax.orders WHERE tenant_id = 1 AND order_id = 20000011;
UPDATE ax.orders SET quantity = 9 WHERE tenant_id = 1 AND order_id = 20000012;
\i :here/check10m.sql

\set case A11_rollback
BEGIN;
INSERT INTO ax.orders VALUES (1, 20000020, 1, 7, 'paid', 1, 1000, '2026-09-05 10:00+00');
UPDATE ax.orders SET status = 'cancelled' WHERE tenant_id = 1 AND order_id = 20000020;
ROLLBACK;
\i :here/check10m.sql

\set case A12_failed_refresh_then_retry
INSERT INTO ax.orders VALUES (1, 20000030, 1, 8, 'paid', 1, 1000, '2026-09-06 10:00+00');
UPDATE ax.orders SET status = 'cancelled' WHERE tenant_id = 1 AND order_id = 20000030;
\set ON_ERROR_STOP off
SET statement_timeout = '1ms';
SELECT pgtrickle.refresh_stream_table('ax.st_day_product_status');
RESET statement_timeout;
\set ON_ERROR_STOP on
\i :here/check10m.sql

\set case A13_pk_change
UPDATE ax.orders SET order_id = 20000040 WHERE tenant_id = 1 AND order_id = :o32;
\i :here/check10m.sql

\set case A14a_I_D_I_D_I_same_window
INSERT INTO ax.orders VALUES (1, 20000050, 1, 9, 'paid', 1, 1000, '2026-09-06 11:00+00');
UPDATE ax.orders SET status = 'cancelled' WHERE tenant_id = 1 AND order_id = 20000050;
UPDATE ax.orders SET status = 'paid' WHERE tenant_id = 1 AND order_id = 20000050;
\i :here/check10m.sql

\set case A14b_D_I_D_existing_same_window
UPDATE ax.orders SET status = 'shipped' WHERE tenant_id = 1 AND order_id = :o37;
UPDATE ax.orders SET status = 'pending' WHERE tenant_id = 1 AND order_id = :o37;
DELETE FROM ax.orders WHERE tenant_id = 1 AND order_id = :o37;
\i :here/check10m.sql

\set case A14c_five_orders_mixed_same_window
INSERT INTO ax.orders SELECT 1, 20000060 + n, 1, 10, 'paid', 1, 1000, '2026-09-07 08:00+00' FROM generate_series(1, 5) n;
UPDATE ax.orders SET status = 'cancelled' WHERE tenant_id = 1 AND order_id IN (20000061, 20000062, 20000063);
UPDATE ax.orders SET status = 'refunded' WHERE tenant_id = 1 AND order_id = 20000061;
DELETE FROM ax.orders WHERE tenant_id = 1 AND order_id = 20000064;
\i :here/check10m.sql

\set case A14d_long_history_existing
UPDATE ax.orders SET status = 'shipped'   WHERE tenant_id = 1 AND order_id = :o42;
UPDATE ax.orders SET status = 'cancelled' WHERE tenant_id = 1 AND order_id = :o42;
UPDATE ax.orders SET status = 'refunded'  WHERE tenant_id = 1 AND order_id = :o42;
UPDATE ax.orders SET status = 'pending'   WHERE tenant_id = 1 AND order_id = :o42;
UPDATE ax.orders SET quantity = 4         WHERE tenant_id = 1 AND order_id = :o42;
\i :here/check10m.sql

\set case A14e_two_tenants_same_window
INSERT INTO ax.orders VALUES (2, 20000070, 1, 1, 'paid', 1, 500, '2026-09-02 10:00+00');
UPDATE ax.orders SET status = 'cancelled' WHERE tenant_id = 2 AND order_id = 20000070;
UPDATE ax.orders SET status = 'refunded' WHERE tenant_id = 2 AND order_id = :t2;
\i :here/check10m.sql
