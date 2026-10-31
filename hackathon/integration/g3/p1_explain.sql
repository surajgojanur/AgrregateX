-- P1 investigation (#28): the shape of pg_trickle 0.108.3's aggregate delta join, read-only.
-- pg_trickle joins the delta groups to the existing stream-table rows on
--   st.<key> IS NOT DISTINCT FROM d.<key>   (src/dvm/operators/aggregate.rs, null-safe, unconditional)
-- PostgreSQL cannot hash, merge or index that predicate, so the join is a nested loop over the
-- whole stream table for every delta group. This script compares it with plain equality, which is
-- equivalent here because every group key of these stream tables is NOT NULL in the source.
-- Runs inside a transaction that is ROLLED BACK; creates only a temp table. Disposable DB only.
-- usage: psql -h 127.0.0.1 -p <shard A port> -U postgres -d aggregatex -f p1_explain.sql
\set ON_ERROR_STOP 1
\timing on
BEGIN;
SELECT count(*) AS stream_table_rows FROM ax.st_day_product_status;

-- Simulated delta: N existing groups (a realistic refresh touches tens to thousands of groups).
\if :{?groups}
\else
  \set groups 500
\endif
CREATE TEMP TABLE d ON COMMIT DROP AS
  SELECT tenant_id, utc_day, product_id, status FROM ax.st_day_product_status ORDER BY random() LIMIT :groups;
ANALYZE d;

\echo '--- (1) IS NOT DISTINCT FROM: what pg_trickle 0.108.3 generates'
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, SUMMARY ON)
SELECT count(st.order_count) FROM d LEFT JOIN ax.st_day_product_status st
  ON  st.tenant_id  IS NOT DISTINCT FROM d.tenant_id
  AND st.utc_day    IS NOT DISTINCT FROM d.utc_day
  AND st.product_id IS NOT DISTINCT FROM d.product_id
  AND st.status     IS NOT DISTINCT FROM d.status;

\echo '--- (2) plain equality: valid because all group keys are NOT NULL (P1 option 1)'
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, SUMMARY ON)
SELECT count(st.order_count) FROM d LEFT JOIN ax.st_day_product_status st
  ON  st.tenant_id = d.tenant_id AND st.utc_day = d.utc_day
  AND st.product_id = d.product_id AND st.status = d.status;

\echo '--- (3) proof the keys are NOT NULL (equality is then exactly equivalent)'
SELECT count(*) FILTER (WHERE tenant_id IS NULL OR utc_day IS NULL OR product_id IS NULL OR status IS NULL)
       AS null_group_keys_in_stream_table
  FROM ax.st_day_product_status;
SELECT attname, attnotnull FROM pg_attribute
 WHERE attrelid = 'ax.orders'::regclass AND attname IN ('tenant_id','utc_day','product_id','status') ORDER BY 1;
ROLLBACK;
