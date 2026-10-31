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
"${P[@]}" -v tenants="${AX_SEED_TENANTS:-10}" -v orders="${AX_SEED_ORDERS:-100000}" -f /ax/seed.sql
"${P[@]}" -f $S/05_bucket_columns.sql
"${P[@]}" -v mode=DIFFERENTIAL -v sched=1s -v cdc=trigger -f $S/10_stream_tables.sql
"${P[@]}" -f $S/20_security.sql
"${P[@]}" -f $S/25_app_roles.sql
"${P[@]}" -c "SELECT pgtrickle.reinitialize_stream_table(n) FROM unnest(ARRAY['ax.st_day_product_status','ax.st_day_category_status','ax.st_hour_category_status']) n"
"${P[@]}" -f $S/30_oracle.sql
# psql variables (:'x') quote the values safely.
"${P[@]}" -v a="$AX_API_PASSWORD" -v w="$AX_WRITER_PASSWORD" -v m="$AX_MONITOR_PASSWORD" <<'SQL'
ALTER ROLE ax_api     PASSWORD :'a';
ALTER ROLE ax_writer  PASSWORD :'w';
ALTER ROLE ax_monitor PASSWORD :'m';
SQL
echo "AgrregateX demo database initialised."
