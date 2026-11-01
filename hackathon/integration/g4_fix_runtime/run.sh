#!/usr/bin/env bash
# #54/#67 runtime regression on a THROWAWAY native PostgreSQL 18 (Homebrew), never a shared database.
# usage: run.sh <label> <pg_trickle source dir>   e.g. run.sh patched ~/Downloads/mitigata/AgrregateX-fix54
# Builds + installs pg_trickle from <src> into Homebrew postgresql@18, starts a private instance on a unix
# 127.0.0.1:55432 (TCP only) in the scratch dir, runs fixture -> cases -> RLS, writes results/<label>/.
set -euo pipefail
LABEL=$1; SRC=$2
HERE=$(cd "$(dirname "$0")" && pwd); SQLDIR=$(cd "$HERE/../../sql" && pwd)
SCRATCH=${AX_SCRATCH:?set AX_SCRATCH to a private scratch dir}
PGC=$(brew --prefix postgresql@18)/bin/pg_config; BIN=$($PGC --bindir)
OUT=$HERE/results/$LABEL; mkdir -p "$OUT"; DATA=$SCRATCH/pg-$LABEL
# One build dir PER LABEL: a shared dir let cargo reuse the other checkout's pg_trickle binary (seen 2026-11-01).
export PATH=$HOME/.cargo/bin:$PATH CARGO_TARGET_DIR=$SCRATCH/pgrx-target-$LABEL
[ ! -e "$DATA" ] || { echo "REFUSED: $DATA exists (no silent reuse)"; exit 3; }
log(){ echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$OUT/run.log"; }
log "source $(git -C "$SRC" rev-parse HEAD) $(git -C "$SRC" log -1 --format=%s | cut -c1-80)"
log "swap: $(sysctl -n vm.swapusage)"
( cd "$SRC" && cargo pgrx install --release --pg-config "$PGC" ) > "$OUT/build.log" 2>&1 || { log "BUILD FAILED"; tail -20 "$OUT/build.log"; exit 4; }
SHA=$(shasum -a 256 "$($PGC --pkglibdir)/pg_trickle.dylib" | cut -d' ' -f1); log "installed pg_trickle.dylib sha256 $SHA"
# Guard: a run must not test a binary already tested under another label (AX_FORBID_SHA = that binary's sha256).
[ -z "${AX_FORBID_SHA:-}" ] || [ "$SHA" != "$AX_FORBID_SHA" ] || { log "REFUSED: installed binary is the forbidden (other-label) build"; exit 7; }
"$BIN/initdb" -D "$DATA" -U postgres --auth=trust -E UTF8 --locale=C > "$OUT/initdb.log"
cat >> "$DATA/postgresql.conf" <<CONF
port = 55432
listen_addresses = '127.0.0.1'
unix_socket_directories = ''   # TCP on 127.0.0.1 only (macOS socket paths max 103 bytes)
shared_preload_libraries = 'pg_trickle'
pg_trickle.enabled = off
shared_buffers = 128MB
max_connections = 20
CONF
"$BIN/pg_ctl" -D "$DATA" -l "$OUT/server.log" -w start > /dev/null || { log "SERVER START FAILED"; tail -5 "$OUT/server.log"; exit 6; }
trap '"$BIN/pg_ctl" -D "$DATA" -m fast -w stop >/dev/null 2>&1 || true' EXIT
Q=("$BIN/psql" -X -h 127.0.0.1 -p 55432 -U postgres -v ON_ERROR_STOP=1)
"${Q[@]}" -d postgres -qc "CREATE DATABASE ax_g4_regress"
"${Q[@]}" -d ax_g4_regress -Atc "select version()" -c "show pg_trickle.enabled" | tee -a "$OUT/run.log"
"${Q[@]}" -d ax_g4_regress -v sqldir="$SQLDIR" -f "$HERE/fixture.sql" > "$OUT/fixture.log" 2>&1 || { log "FIXTURE FAILED"; tail "$OUT/fixture.log"; exit 5; }
"${Q[@]}" -d ax_g4_regress -Atc "select extversion from pg_extension where extname='pg_trickle'" | sed 's/^/extversion /' | tee -a "$OUT/run.log"
"${Q[@]}" -d ax_g4_regress -v here="$HERE" -f "$HERE/cases.sql" > "$OUT/cases.log" 2>&1 || { log "CASES ABORTED"; tail "$OUT/cases.log"; }
"${Q[@]}" -d ax_g4_regress -f "$HERE/rls.sql" > "$OUT/rls.log" 2>&1 || log "RLS SCRIPT FAILED"
"${Q[@]}" -d ax_g4_regress -c "SELECT case_id, product, category, hour, non_differential, ok FROM g4r.results ORDER BY at" | tee "$OUT/summary.txt"
"${Q[@]}" -d ax_g4_regress -Atc "SELECT json_agg(r ORDER BY at) FROM g4r.results r" > "$OUT/results.json"
grep -E "^ (tenant|no_tenant|setting)" "$OUT/rls.log" | tee -a "$OUT/summary.txt" || true
log "cases ok: $("${Q[@]}" -d ax_g4_regress -Atc "SELECT count(*) FILTER (WHERE ok) || '/' || count(*) FROM g4r.results")"
