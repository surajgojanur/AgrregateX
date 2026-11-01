#!/usr/bin/env bash
# G4 fix regression on 10,000,000 synthetic orders / 10 tenants, on a THROWAWAY native PostgreSQL 18.
# Uses the pg_trickle already installed in Homebrew postgresql@18 (checked by sha256), no rebuild.
# usage: AX_SCRATCH=<private dir> AX_EXPECT_SHA=<sha256 of pg_trickle.dylib> ./run10m.sh <label>
# Stops itself if free disk < 4 GiB or swap free < 512 MB (operator-approved limits for this run).
set -euo pipefail
LABEL=$1; HERE=$(cd "$(dirname "$0")" && pwd); SQLDIR=$(cd "$HERE/../../../sql" && pwd)
GEN=$(cd "$HERE/../../scale" && pwd)/gen_synthetic.sql
SCRATCH=${AX_SCRATCH:?}; PGC=$(brew --prefix postgresql@18)/bin/pg_config; BIN=$($PGC --bindir)
OUT=$HERE/results/$LABEL; DATA=$SCRATCH/pg10m-$LABEL; mkdir -p "$OUT"
[ ! -e "$DATA" ] || { echo "REFUSED: $DATA exists"; exit 3; }
log(){ echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$OUT/run.log"; }
SHA=$(shasum -a 256 "$($PGC --pkglibdir)/pg_trickle.dylib" | cut -d' ' -f1); log "pg_trickle.dylib sha256 $SHA"
[ "$SHA" = "${AX_EXPECT_SHA:?}" ] || { log "REFUSED: installed binary is not the expected build"; exit 7; }
log "disk free $(df -g ~ | tail -1 | awk '{print $4}') GiB; $(sysctl -n vm.swapusage)"
"$BIN/initdb" -D "$DATA" -U postgres --auth=trust -E UTF8 --locale=C > "$OUT/initdb.log"
cat >> "$DATA/postgresql.conf" <<CONF
port = 55432
listen_addresses = '127.0.0.1'
unix_socket_directories = ''
shared_preload_libraries = 'pg_trickle'
pg_trickle.enabled = off
shared_buffers = 128MB
work_mem = 16MB
maintenance_work_mem = 128MB
hash_mem_multiplier = 1.0
max_parallel_workers_per_gather = 0
wal_level = minimal
max_wal_senders = 0
max_wal_size = 1GB
synchronous_commit = off
max_connections = 20
CONF
"$BIN/pg_ctl" -D "$DATA" -l "$OUT/server.log" -w start > /dev/null || { log "SERVER START FAILED"; exit 6; }
stop(){ "$BIN/pg_ctl" -D "$DATA" -m fast -w stop >/dev/null 2>&1 || true; }
trap stop EXIT
# watchdog: approved limits for this run
( while kill -0 $$ 2>/dev/null; do
    d=$(df -m ~ | tail -1 | awk '{print $4}'); s=$(sysctl -n vm.swapusage | sed -E 's/.*free = ([0-9]+).*/\1/')
    if [ "$d" -lt 4096 ] || [ "$s" -lt 512 ]; then echo "[$(date -u +%H:%M:%S)] WATCHDOG STOP: disk ${d}MB swap ${s}MB" >> "$OUT/run.log"; stop; exit; fi
    sleep 5; done ) &
Q=("$BIN/psql" -X -h 127.0.0.1 -p 55432 -U postgres -v ON_ERROR_STOP=1)
D=(-d ax_g4_regress)
"${Q[@]}" -d postgres -qc "CREATE DATABASE ax_g4_regress"
t(){ local s=$(date +%s); "$@"; log "  took $(( $(date +%s)-s ))s"; }
log "schema + generate ${AX_ORDERS:-10000000} orders / 10 tenants (seed 42, Zipf 1.0)"
t "${Q[@]}" "${D[@]}" -q -c "CREATE EXTENSION pg_trickle" -f "$SQLDIR/00_schema.sql" -f "$SQLDIR/05_bucket_columns.sql" > "$OUT/schema.log" 2>&1
t "${Q[@]}" "${D[@]}" -v orders=${AX_ORDERS:-10000000} -v tenants=10 -v seed=42 -v zipf_s=1.0 -v chunk=250000 -f "$GEN" > "$OUT/generate.log" 2>&1
"${Q[@]}" "${D[@]}" -Atc "SELECT 'orders=' || count(*) FROM ax.orders" -c "SELECT string_agg(tenant_id || ':' || n, ' ' ORDER BY tenant_id) FROM (SELECT tenant_id, count(*) n FROM ax.orders GROUP BY 1) x" | tee -a "$OUT/run.log"
log "stream tables, RLS, roles, initial populate (FULL, expected; sort-based, spills to disk, low RAM)"
PGOPTIONS="-c enable_hashagg=off -c enable_hashjoin=off" t "${Q[@]}" "${D[@]}" -q -v mode=DIFFERENTIAL -v sched=1h -v cdc=trigger -f "$SQLDIR/10_stream_tables.sql" -f "$SQLDIR/20_security.sql" -f "$SQLDIR/25_app_roles.sql" \
   -c "SELECT pgtrickle.reinitialize_stream_table(n) FROM unnest(ARRAY['ax.st_day_product_status','ax.st_day_category_status','ax.st_hour_category_status']) n" \
   -c "SELECT pgtrickle.refresh_stream_table(n) FROM unnest(ARRAY['ax.st_day_product_status','ax.st_day_category_status','ax.st_hour_category_status']) n" \
   -f "$SQLDIR/30_oracle.sql" -c "ANALYZE" > "$OUT/streams.log" 2>&1
"${Q[@]}" "${D[@]}" -Atc "SELECT pg_size_pretty(pg_database_size(current_database()))" | sed 's/^/db size /' | tee -a "$OUT/run.log"
log "FULL 10M oracle BEFORE cases"
t "${Q[@]}" "${D[@]}" -f "$HERE/oracle_lowmem.sql" > "$OUT/oracle-before.txt" 2>&1; grep -E "st_(day|hour)" "$OUT/oracle-before.txt" | tee -a "$OUT/run.log"
"${Q[@]}" "${D[@]}" -q -c "CREATE SCHEMA g4r" \
  -c "CREATE TABLE g4r.results (case_id text, product text, category text, hour text, actions text, non_differential int, ok boolean, at timestamptz DEFAULT clock_timestamp())" \
  -c "CREATE TABLE g4r.mark (refresh_id bigint)" -c "INSERT INTO g4r.mark SELECT coalesce(max(refresh_id), 0) FROM pgtrickle.pgt_refresh_history" \
  -f "$HERE/scoped_oracle.sql" -f "$HERE/pick.sql"
"${Q[@]}" "${D[@]}" -Atc "SELECT '\\set ' || k || ' ' || order_id FROM g4r.pick ORDER BY k" > "$OUT/picks.sql"; tr '\n' ' ' < "$OUT/picks.sql" | sed 's/^/picks: /' | tee -a "$OUT/run.log"; echo
log "22 cases (one refresh window each; scoped oracle after each)"
t "${Q[@]}" "${D[@]}" -v here="$HERE" -f "$OUT/picks.sql" -f "$HERE/cases10m.sql" > "$OUT/cases.log" 2>&1 || log "CASES ABORTED (see cases.log)"
log "FULL 10M oracle AFTER cases"
t "${Q[@]}" "${D[@]}" -f "$HERE/oracle_lowmem.sql" > "$OUT/oracle-after.txt" 2>&1; grep -E "st_(day|hour)" "$OUT/oracle-after.txt" | tee -a "$OUT/run.log"
"${Q[@]}" "${D[@]}" -f "$HERE/../rls.sql" > "$OUT/rls.log" 2>&1 || log "RLS SCRIPT FAILED"
"${Q[@]}" "${D[@]}" -c "SELECT case_id, product, category, hour, non_differential, ok FROM g4r.results ORDER BY at" | tee "$OUT/summary.txt"
"${Q[@]}" "${D[@]}" -Atc "SELECT json_agg(r ORDER BY at) FROM g4r.results r" > "$OUT/results.json"
grep -E "^ (tenant|no_tenant|setting)" "$OUT/rls.log" | tee -a "$OUT/summary.txt" || true
log "cases ok: $("${Q[@]}" "${D[@]}" -Atc "SELECT count(*) FILTER (WHERE ok) || '/' || count(*) FROM g4r.results")"
