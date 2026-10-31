#!/usr/bin/env bash
# Opus P1 A/B correctness + effective-mode run against the disposable spike DB.
# usage: ab_run.sh <MODE> <SCHED> <CDC> <N_MUTATIONS> <DIM_CHURN true|false> [label]
set -euo pipefail
MODE=$1 SCHED=$2 CDC=$3 N=$4 CHURN=$5 LABEL=${6:-$MODE-$SCHED-$CDC}
HERE=$(cd "$(dirname "$0")" && pwd); SQL=$HERE/../sql
: "${PGHOST:=127.0.0.1}" "${PGPORT:=25540}" "${PGUSER:=postgres}" "${PGDATABASE:=tenant_shared}"
: "${PGPASSWORD:=spike-only-not-secret}"; export PGHOST PGPORT PGUSER PGDATABASE PGPASSWORD
P="psql -X -q -v ON_ERROR_STOP=1"
mkdir -p "$HERE/results"; OUT=$HERE/results/ab-$LABEL.txt
{
  echo "# $LABEL  mode=$MODE sched=$SCHED cdc=$CDC mutations=$N dim_churn=$CHURN  $(date -u +%FT%TZ)"
  $P -f "$SQL/90_drop_stream_tables.sql" >/dev/null
  $P -v mode="$MODE" -v sched="$SCHED" -v cdc="$CDC" -f "$SQL/10_stream_tables.sql" >/dev/null
  $P -f "$SQL/30_oracle.sql" -f "$HERE/spike_lib.sql" >/dev/null 2>&1
  $P -c "select pgt_name, refresh_mode, effective_refresh_mode, requested_cdc_mode, status from pgtrickle.pgt_stream_tables where pgt_schema='ax' order by 1"
  T0=$($P -At -c "select now()")
  S=$(python3 -c "import time;print(time.time())")
  $P -c "call ax_spike.mutate($N, 200, $CHURN)"
  E=$(python3 -c 'import time;print(time.time())')
  echo "mutation wall seconds: $(python3 -c "print(round($E-$S,3))")"
  $P -c "select round(ax_spike.wait_fresh(now(), 120)::numeric,3) as wait_fresh_s"
  $P -c "select * from ax.oracle_mismatches()"
  $P -c "select * from ax.refresh_audit('$T0') where action <> 'NO_DATA'"
} 2>&1 | tee "$OUT"
