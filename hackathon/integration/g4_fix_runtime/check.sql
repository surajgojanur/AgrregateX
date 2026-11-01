-- Refresh all three stream tables once (one refresh window), then record the oracle and the refresh actions.
-- Usage: \set case X  \i check.sql
SELECT pgtrickle.refresh_stream_table('ax.st_day_product_status');
SELECT pgtrickle.refresh_stream_table('ax.st_day_category_status');
SELECT pgtrickle.refresh_stream_table('ax.st_hour_category_status');
WITH o AS (SELECT stream_table, missing_in_st || '/' || extra_in_st AS d,
                  missing_in_st + extra_in_st = 0 AS clean FROM ax.oracle_mismatches()),
     h AS (SELECT string_agg(p.pgt_name || ':' || h.action || ':' || coalesce(h.merge_strategy_used, '-') || ':' || h.status,
                             ' ' ORDER BY h.refresh_id) AS actions,
                  count(*) FILTER (WHERE h.action NOT IN ('DIFFERENTIAL', 'NO_DATA')) AS non_diff
             FROM pgtrickle.pgt_refresh_history h JOIN pgtrickle.pgt_stream_tables p USING (pgt_id)
            WHERE h.refresh_id > (SELECT refresh_id FROM g4r.mark))
INSERT INTO g4r.results (case_id, product, category, hour, actions, non_differential, ok)
SELECT :'case',
       (SELECT d FROM o WHERE stream_table = 'st_day_product_status'),
       (SELECT d FROM o WHERE stream_table = 'st_day_category_status'),
       (SELECT d FROM o WHERE stream_table = 'st_hour_category_status'),
       h.actions, h.non_diff, (SELECT bool_and(clean) FROM o) AND h.non_diff = 0
  FROM h;
UPDATE g4r.mark SET refresh_id = (SELECT coalesce(max(refresh_id), 0) FROM pgtrickle.pgt_refresh_history);
SELECT case_id, product, category, hour, non_differential, ok FROM g4r.results WHERE case_id = :'case';
-- Isolate cases: if this case left drift, repair it (reinitialise = full recompute) and confirm a clean slate
-- BEFORE the next case. The repair's own FULL/REINIT history is excluded from the next case by moving the mark.
SELECT NOT ok AS needs_repair FROM g4r.results WHERE case_id = :'case' \gset
\if :needs_repair
  SELECT pgtrickle.reinitialize_stream_table(n)
    FROM unnest(ARRAY['ax.st_day_product_status','ax.st_day_category_status','ax.st_hour_category_status']) n;
  SELECT pgtrickle.refresh_stream_table(n)
    FROM unnest(ARRAY['ax.st_day_product_status','ax.st_day_category_status','ax.st_hour_category_status']) n;
  UPDATE g4r.mark SET refresh_id = (SELECT coalesce(max(refresh_id), 0) FROM pgtrickle.pgt_refresh_history);
  SELECT bool_and(missing_in_st + extra_in_st = 0) AS clean_after_repair FROM ax.oracle_mismatches() \gset
  UPDATE g4r.results SET actions = actions || ' | repaired_clean=' || :'clean_after_repair' WHERE case_id = :'case';
\endif
