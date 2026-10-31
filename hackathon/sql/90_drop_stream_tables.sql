-- Drop AgrregateX stream tables (spike/reset only).
SELECT pgtrickle.drop_stream_table(n) FROM unnest(ARRAY[
  'ax.st_hour_category_status','ax.st_day_category_status','ax.st_day_product_status']) n
WHERE EXISTS (SELECT 1 FROM pgtrickle.pgt_stream_tables s WHERE s.pgt_schema||'.'||s.pgt_name = n);
