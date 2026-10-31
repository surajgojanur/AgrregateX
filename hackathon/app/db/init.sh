#!/usr/bin/env bash
# First-boot initialisation for the AgrregateX demo database (docker-entrypoint-initdb.d).
# Order matters (handoff F7): schema -> seed -> bucket columns -> stream tables -> RLS + roles
# -> reinitialize (RLS on sources suspends stream tables) -> oracle helpers.
set -euo pipefail
: "${AX_API_PASSWORD:?set AX_API_PASSWORD}" "${AX_WRITER_PASSWORD:?set AX_WRITER_PASSWORD}" "${AX_MONITOR_PASSWORD:?set AX_MONITOR_PASSWORD}"
P=(psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -q)
S=/ax/sql
"${P[@]}" -c "CREATE EXTENSION IF NOT EXISTS pg_trickle"
"${P[@]}" -f $S/00_schema.sql
if [ "${AX_SEED_MODE:-}" = "synthetic" ]; then
  # Scale datasets (1M/10, 10M/100): deterministic, chunked, resumable synthetic generator.
  # Bucket columns are created on the EMPTY table first (the generator fills them itself), so
  # the 05 backfill below updates nothing instead of rewriting millions of rows.
  "${P[@]}" -f $S/05_bucket_columns.sql
  "${P[@]}" -v orders="${AX_SEED_ORDERS:-1000000}" -v tenants="${AX_SEED_TENANTS:-10}" \
    -v seed="${AX_SEED:-42}" -v zipf_s="${AX_SEED_ZIPF_S:-1.0}" -v chunk="${AX_SEED_CHUNK:-250000}" \
    -v shard_tenants="${AX_SHARD_TENANTS:-}" -f /ax/gen_synthetic.sql
elif [ -n "${AX_SHARD_TENANTS:-}" ]; then
  # Sharded mode: same deterministic global dataset, filtered to this shard's tenants.
  "${P[@]}" -v tenants="$AX_SHARD_TENANTS" -v orders="${AX_SEED_ORDERS:-10000}" -v all_tenants="${AX_SEED_TENANTS:-10}" -f /ax/seed_shard.sql
else
  "${P[@]}" -v tenants="${AX_SEED_TENANTS:-10}" -v orders="${AX_SEED_ORDERS:-100000}" -f /ax/seed.sql
fi
"${P[@]}" -f $S/05_bucket_columns.sql
"${P[@]}" -v mode=DIFFERENTIAL -v sched=1s -v cdc=trigger -f $S/10_stream_tables.sql
"${P[@]}" -f $S/20_security.sql
"${P[@]}" -f $S/25_app_roles.sql
"${P[@]}" -c "SELECT pgtrickle.reinitialize_stream_table(n) FROM unnest(ARRAY['ax.st_day_product_status','ax.st_day_category_status','ax.st_hour_category_status']) n"
"${P[@]}" -f $S/30_oracle.sql
if [ -n "${AX_SHARD_SEQ_START:-}" ]; then   # disjoint new order ids per shard
  "${P[@]}" -c "ALTER SEQUENCE ax.order_id_seq RESTART WITH ${AX_SHARD_SEQ_START}"
fi
# psql variables (:'x') quote the values safely.
"${P[@]}" -v a="$AX_API_PASSWORD" -v w="$AX_WRITER_PASSWORD" -v m="$AX_MONITOR_PASSWORD" <<'SQL'
ALTER ROLE ax_api     PASSWORD :'a';
ALTER ROLE ax_writer  PASSWORD :'w';
ALTER ROLE ax_monitor PASSWORD :'m';
SQL
echo "AgrregateX demo database initialised."
