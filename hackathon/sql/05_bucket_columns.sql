-- AgrregateX ENGINE_CONTRACT v1 — derived bucket columns on the source table.
--
-- WHY (measured on pg_trickle 0.108.3, see docs/handoffs/opus.md §Findings):
--  * GROUP BY date_trunc(...) directly      -> refresh falls back to FULL
--    (DISTINCT_AGG_BOUNDED_STATE_FULL_FALLBACK: "GROUP BY key is not a simple column").
--  * same expression inside a subquery       -> stays DIFFERENTIAL but the MERGE joins on
--    nullable IS NOT DISTINCT FROM keys -> unhashable nested loop: 8.7k deltas = 31 s.
--  * GENERATED ALWAYS ... STORED columns     -> CDC change buffer does not capture them;
--    stream tables go to permanent ERROR ("column c.utc_day does not exist").
-- => plain NOT NULL columns maintained by a BEFORE ROW trigger. CDC sees final row values.
-- Cost: one PL/pgSQL BEFORE trigger per written order row (quantified by the G-3 A/B).
-- The trigger is authoritative: client-supplied values for these columns are overwritten.

ALTER TABLE ax.orders
    ADD COLUMN IF NOT EXISTS utc_day    timestamp,
    ADD COLUMN IF NOT EXISTS utc_hour   timestamp,
    ADD COLUMN IF NOT EXISTS line_cents bigint;

CREATE OR REPLACE FUNCTION ax.orders_derive_buckets() RETURNS trigger
LANGUAGE plpgsql AS $f$
BEGIN
    NEW.utc_hour   := date_trunc('hour', NEW.created_at AT TIME ZONE 'UTC');
    NEW.utc_day    := date_trunc('day',  NEW.created_at AT TIME ZONE 'UTC');
    NEW.line_cents := NEW.quantity::bigint * NEW.unit_price_cents;
    RETURN NEW;
END $f$;

-- Backfill existing rows once (before the trigger exists, so no double work).
UPDATE ax.orders
   SET utc_hour   = date_trunc('hour', created_at AT TIME ZONE 'UTC'),
       utc_day    = date_trunc('day',  created_at AT TIME ZONE 'UTC'),
       line_cents = quantity::bigint * unit_price_cents
 WHERE utc_day IS NULL OR utc_hour IS NULL OR line_cents IS NULL;

ALTER TABLE ax.orders
    ALTER COLUMN utc_day    SET NOT NULL,
    ALTER COLUMN utc_hour   SET NOT NULL,
    ALTER COLUMN line_cents SET NOT NULL;

DROP TRIGGER IF EXISTS orders_derive_buckets ON ax.orders;
CREATE TRIGGER orders_derive_buckets
    BEFORE INSERT OR UPDATE OF created_at, quantity, unit_price_cents, utc_day, utc_hour, line_cents
    ON ax.orders FOR EACH ROW EXECUTE FUNCTION ax.orders_derive_buckets();

VACUUM ANALYZE ax.orders;
