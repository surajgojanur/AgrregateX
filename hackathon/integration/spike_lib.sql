-- Opus P1 spike helpers (test-only; never install in a judged/production DB).
CREATE SCHEMA IF NOT EXISTS ax_spike;

-- Probe tenant used only for lag measurement (tenant 999, product 1, category 1).
INSERT INTO ax.tenants VALUES (999, 'lag-probe') ON CONFLICT DO NOTHING;
INSERT INTO ax.products VALUES (999, 1, 1, 'probe') ON CONFLICT DO NOTHING;
INSERT INTO ax.customers VALUES (999, 1, 'probe') ON CONFLICT DO NOTHING;

-- Random mixed mutation batch covering every correctness hazard:
-- insert, cancel, refund, quantity change, price change, bucket move (created_at),
-- product move (category change through the join), hard delete, dimension update.
CREATE OR REPLACE PROCEDURE ax_spike.mutate(n int, batch int DEFAULT 200, dim_churn bool DEFAULT true)
LANGUAGE plpgsql AS $p$
DECLARE
    i int := 0; op int; t int; oid_ bigint; maxid bigint;
BEGIN
    SELECT max(order_id) INTO maxid FROM ax.orders;
    WHILE i < n LOOP
        op := floor(random() * CASE WHEN dim_churn THEN 9 ELSE 8 END)::int;
        t  := CASE WHEN random() < 0.4 THEN 1 ELSE 1 + floor(random() * 10)::int END;
        SELECT order_id INTO oid_ FROM ax.orders
         WHERE tenant_id = t AND order_id >= floor(random() * maxid)::bigint
         ORDER BY order_id LIMIT 1;
        IF op = 0 OR oid_ IS NULL THEN
            maxid := maxid + 1;
            INSERT INTO ax.orders VALUES (t, maxid, 1 + floor(random()*1000)::int,
                1 + floor(random()*200)::int, 'paid', 1 + floor(random()*5)::int,
                100 + floor(random()*99900)::bigint,
                timestamptz '2026-08-02 00:00:00+00' + random() * interval '90 days', now());
        ELSIF op = 1 THEN
            UPDATE ax.orders SET status = 'cancelled', updated_at = now() WHERE tenant_id = t AND order_id = oid_;
        ELSIF op = 2 THEN
            UPDATE ax.orders SET status = 'refunded', updated_at = now() WHERE tenant_id = t AND order_id = oid_;
        ELSIF op = 3 THEN
            UPDATE ax.orders SET quantity = 1 + floor(random()*9)::int WHERE tenant_id = t AND order_id = oid_;
        ELSIF op = 4 THEN
            UPDATE ax.orders SET unit_price_cents = 100 + floor(random()*99900)::bigint WHERE tenant_id = t AND order_id = oid_;
        ELSIF op = 5 THEN  -- crosses hour/day buckets
            UPDATE ax.orders SET created_at = created_at + (random() * interval '3 days' - interval '36 hours')
             WHERE tenant_id = t AND order_id = oid_;
        ELSIF op = 6 THEN  -- product (and therefore category) move
            UPDATE ax.orders SET product_id = 1 + floor(random()*200)::int WHERE tenant_id = t AND order_id = oid_;
        ELSIF op = 7 THEN
            DELETE FROM ax.orders WHERE tenant_id = t AND order_id = oid_;
        ELSE              -- dimension change: product recategorised
            UPDATE ax.products SET category_id = 1 + floor(random()*12)::int
             WHERE tenant_id = t AND product_id = 1 + floor(random()*200)::int;
        END IF;
        i := i + 1;
        IF i % batch = 0 THEN COMMIT; END IF;
    END LOOP;
    COMMIT;
END $p$;

-- Wait until every ax stream table has COMPLETED a refresh (any action, incl. NO_DATA)
-- that STARTED after target. NOTE: pgt_stream_tables.data_timestamp / pgt_status().staleness
-- do NOT advance on NO_DATA refreshes, so they overstate staleness on idle tables.
CREATE OR REPLACE FUNCTION ax_spike.wait_fresh(target timestamptz, timeout_s float8 DEFAULT 60)
RETURNS float8 LANGUAGE plpgsql AS $f$
DECLARE t0 timestamptz := clock_timestamp();
BEGIN
    LOOP
        EXIT WHEN NOT EXISTS (
            SELECT 1 FROM pgtrickle.pgt_stream_tables st
            WHERE st.pgt_schema = 'ax'
              AND NOT EXISTS (SELECT 1 FROM pgtrickle.pgt_refresh_history h
                              WHERE h.pgt_id = st.pgt_id AND h.status = 'COMPLETED'
                                AND h.start_time > target));
        IF extract(epoch FROM clock_timestamp() - t0) > timeout_s THEN
            RAISE EXCEPTION 'wait_fresh timeout after % s', timeout_s;
        END IF;
        PERFORM pg_sleep(0.02);
    END LOOP;
    RETURN extract(epoch FROM clock_timestamp() - t0);
END $f$;

CREATE TABLE IF NOT EXISTS ax_spike.lag_samples (
    run_label text, kind text, sample int, lag_ms numeric, recorded_at timestamptz DEFAULT now());

-- Commit→visible lag. Each sample: COMMIT a source change, then poll the stream table
-- (fresh READ COMMITTED snapshot per statement) until the change is visible.
CREATE OR REPLACE PROCEDURE ax_spike.measure_lag(run_label text, samples int DEFAULT 20,
                                                 timeout_s float8 DEFAULT 60)
LANGUAGE plpgsql AS $p$
DECLARE
    s int; before_n numeric; now_n numeric; committed_at timestamptz; oid_ bigint;
BEGIN
    FOR s IN 1..samples LOOP
        -- INSERT lag
        SELECT COALESCE(sum(order_count), 0) INTO before_n FROM ax.st_day_product_status WHERE tenant_id = 999;
        SELECT COALESCE(max(order_id), 0) + 1 INTO oid_ FROM ax.orders WHERE tenant_id = 999;
        INSERT INTO ax.orders VALUES (999, oid_, 1, 1, 'paid', 1, 1000, now(), now());
        COMMIT;
        committed_at := clock_timestamp();
        LOOP
            SELECT COALESCE(sum(order_count), 0) INTO now_n FROM ax.st_day_product_status WHERE tenant_id = 999;
            EXIT WHEN now_n > before_n;
            IF clock_timestamp() - committed_at > make_interval(secs => timeout_s) THEN
                RAISE EXCEPTION 'insert lag timeout (sample %)', s; END IF;
            PERFORM pg_sleep(0.01);
        END LOOP;
        INSERT INTO ax_spike.lag_samples VALUES
            (run_label, 'insert', s, round(extract(epoch FROM clock_timestamp() - committed_at)::numeric * 1000, 1));
        COMMIT;
        -- CANCEL (status update) lag
        SELECT COALESCE(sum(order_count), 0) INTO before_n FROM ax.st_day_product_status
         WHERE tenant_id = 999 AND status = 'cancelled';
        UPDATE ax.orders SET status = 'cancelled' WHERE tenant_id = 999 AND order_id = oid_;
        COMMIT;
        committed_at := clock_timestamp();
        LOOP
            SELECT COALESCE(sum(order_count), 0) INTO now_n FROM ax.st_day_product_status
             WHERE tenant_id = 999 AND status = 'cancelled';
            EXIT WHEN now_n > before_n;
            IF clock_timestamp() - committed_at > make_interval(secs => timeout_s) THEN
                RAISE EXCEPTION 'cancel lag timeout (sample %)', s; END IF;
            PERFORM pg_sleep(0.01);
        END LOOP;
        INSERT INTO ax_spike.lag_samples VALUES
            (run_label, 'cancel', s, round(extract(epoch FROM clock_timestamp() - committed_at)::numeric * 1000, 1));
        COMMIT;
        -- de-phase samples from the scheduler tick
        PERFORM pg_sleep(random() * 0.7);
    END LOOP;
END $p$;

CREATE OR REPLACE VIEW ax_spike.lag_summary AS
SELECT run_label, kind, count(*) AS n,
       percentile_cont(0.5)  WITHIN GROUP (ORDER BY lag_ms) AS p50_ms,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY lag_ms) AS p95_ms,
       max(lag_ms) AS max_ms
FROM ax_spike.lag_samples GROUP BY 1, 2 ORDER BY 1, 2;
