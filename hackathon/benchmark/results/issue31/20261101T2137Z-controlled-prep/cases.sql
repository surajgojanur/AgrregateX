-- PREPARED ONLY. Case A and B use unique keys; no sleeps or scheduler races.
-- Required psql variable phase: A, B_setup, or B_update. No automatic refresh here.
\set ON_ERROR_STOP on
SELECT current_database()='ax_g4_repro' AND current_setting('pg_trickle.enabled',true)='off'
 AND (SELECT count(*) FROM ax.orders)<100 AS allowed \gset
\if :allowed
\else
  \quit 3
\endif
SELECT :'phase'='A' AS case_a, :'phase'='B_setup' AS case_b_setup,
       :'phase'='B_update' AS case_b_update \gset
\if :case_a
  BEGIN;
  INSERT INTO ax.orders(tenant_id,order_id,customer_id,product_id,status,quantity,unit_price_cents,created_at)
    VALUES (1,1001,1,1,'paid',1,1000,'2026-11-20T12:00:00Z');
  COMMIT;
  -- Controller records monotonic COMMIT-return time and source state externally.
  BEGIN;
  UPDATE ax.orders SET status='cancelled',updated_at=clock_timestamp() WHERE tenant_id=1 AND order_id=1001;
  COMMIT;
\elif :case_b_setup
  BEGIN;
  INSERT INTO ax.orders(tenant_id,order_id,customer_id,product_id,status,quantity,unit_price_cents,created_at)
    VALUES (1,1002,1,2,'paid',1,1000,'2026-11-21T12:00:00Z');
  COMMIT;
  -- Controller must refresh all three, capture exact frontiers/oracle=0/0,
  -- and prove the source AND stream contain B paid before invoking B_update.
\elif :case_b_update
  BEGIN;
  UPDATE ax.orders SET status='cancelled',updated_at=clock_timestamp() WHERE tenant_id=1 AND order_id=1002;
  COMMIT;
\else
  \echo 'REFUSED: unrecognized phase'
  \quit 3
\endif
