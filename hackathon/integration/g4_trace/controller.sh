#!/usr/bin/env bash
# Controller for #50 on the approved Mac target only. Deadline 600 s from start; aborts between steps.
set -uo pipefail
P=~/Downloads/mitigata/AgrregateX-g4/hackathon/benchmark/results/issue31/20261101T2137Z-controlled-prep
E=~/Downloads/mitigata/AgrregateX-g4/hackathon/integration/g4_trace
O=/private/tmp/claude-501/-Users-shridharbhat-Downloads-mitigata/63b00d95-40e1-462b-9ad6-11ad60221f8b/scratchpad/g4-override.yaml
C=ax-issue31-g4-repro-db
T0=$(date +%s)
log(){ echo "[$(date -u +%H:%M:%S) +$(( $(date +%s)-T0 ))s] $*" | tee -a $E/controller.log; }
deadline(){ [ $(( $(date +%s)-T0 )) -lt 600 ] || { log "DEADLINE EXCEEDED - aborting before: $1"; exit 9; }; }
q(){ docker exec -i $C psql -X -U postgres -d ax_g4_repro -v ON_ERROR_STOP=1 "$@"; }
step(){ deadline "$1"; log "STEP $1"; }
cd $P
step "start target"
export AX_G4_SUPERUSER_PASSWORD=$(openssl rand -hex 24)   # private throwaway, never printed
docker compose -p ax-issue31-g4-repro -f compose.yaml -f $O up -d db 2>&1 | tail -2 | tee -a $E/controller.log
unset AX_G4_SUPERUSER_PASSWORD
for i in $(seq 1 60); do docker exec $C pg_isready -U postgres -d ax_g4_repro >/dev/null 2>&1 && break; sleep 2; done
docker inspect $C --format 'name={{.Name}} image={{.Image}} platform={{.Platform}} labels={{json .Config.Labels}} ports={{json .NetworkSettings.Ports}} mem={{.HostConfig.Memory}} cpus={{.HostConfig.NanoCpus}}' > $E/00-container.txt
q -Atc "select version()" -c "show pg_trickle.enabled" -c "select current_database()" > $E/01-versions.txt 2>&1; cat $E/01-versions.txt | tee -a $E/controller.log
step "fixture"
q -f /protocol/fixture.sql > $E/02-fixture.txt 2>&1 || { log "fixture exit $?"; exit 4; }
step "baseline checks"
q -f /protocol/oracle_select.sql > $E/03-oracle-baseline.txt 2>&1
q -c "select pgt_name,status,is_populated,needs_reinit,effective_refresh_mode,frontier is not null as has_frontier from pgtrickle.pgt_stream_tables order by 1" -c "select p.pgt_name,h.refresh_id,h.action,h.status,h.initiated_by,h.merge_strategy_used from pgtrickle.pgt_refresh_history h join pgtrickle.pgt_stream_tables p using(pgt_id) order by h.refresh_id" -c "select relrowsecurity,relforcerowsecurity,pg_get_userbyid(relowner) from pg_class where oid='ax.orders'::regclass" > $E/04-baseline-state.txt 2>&1
H1=$(q -Atc "select count(*) from pgtrickle.pgt_refresh_history"); sleep 5; H2=$(q -Atc "select count(*) from pgtrickle.pgt_refresh_history")
log "scheduler idle check: history $H1 -> $H2 (must be equal)"; [ "$H1" = "$H2" ] || { log "ABORT: scheduler-driven refreshes observed"; exit 5; }
grep -E 'st_day|st_hour' $E/03-oracle-baseline.txt | tee -a $E/controller.log
step "case B setup"
q -v phase=B_setup -f /protocol/cases.sql > $E/10-B-setup.txt 2>&1
for s in st_day_product_status st_day_category_status st_hour_category_status; do q -c "select pgtrickle.refresh_stream_table('ax.$s')" >> $E/10-B-setup.txt 2>&1; done
q -f /protocol/oracle_select.sql > $E/11-B-oracle-after-setup.txt 2>&1
q -Atc "select 'B precondition source', status from ax.orders where order_id=1002" -c "select 'B precondition stream', status, order_count from ax.st_day_product_status where tenant_id=1 and utc_day='2026-11-21'" -c "select pgt_name, frontier from pgtrickle.pgt_stream_tables order by 1" >> $E/11-B-oracle-after-setup.txt 2>&1
grep -E 'st_day|st_hour|precondition' $E/11-B-oracle-after-setup.txt | tee -a $E/controller.log
step "case B update"
q -v phase=B_update -f /protocol/cases.sql > $E/12-B-update.txt 2>&1; log "B_update exit $?"
for s in st_day_product_status st_day_category_status st_hour_category_status; do
  step "case B trace $s"
  q -v stream=$s -v experiment=primary_default -v case_id=B_update -f /protocol/trace_refresh.sql > $E/13-B-trace-$s.txt 2>&1; log "trace $s exit $?"
done
q -f /protocol/oracle_select.sql > $E/14-B-oracle-final.txt 2>&1; grep -E 'st_day|st_hour' $E/14-B-oracle-final.txt | tee -a $E/controller.log
step "case A insert+update"
q -v phase=A -f /protocol/cases.sql > $E/20-A-cases.txt 2>&1; log "A cases exit $?"
q -Atc "select 'A source', order_id, status from ax.orders where order_id=1001" >> $E/20-A-cases.txt
for s in st_day_product_status st_day_category_status st_hour_category_status; do
  step "case A trace $s"
  q -v stream=$s -v experiment=primary_default -v case_id=A -f /protocol/trace_refresh.sql > $E/21-A-trace-$s.txt 2>&1; log "trace $s exit $?"
done
q -f /protocol/oracle_select.sql > $E/22-A-oracle-final.txt 2>&1; grep -E 'st_day|st_hour' $E/22-A-oracle-final.txt | tee -a $E/controller.log
step "logs"
docker logs $C 2>&1 | grep -E 'DELTA|delta|MERGE|merge|vector|VECTOR|agg_fast|P5|refreshed|DEBUG:  pg_trickle' | grep -vE 'checkpoint' | cut -c1-2000 | tail -400 > $E/30-server-log-filtered.txt
log "DONE total $(( $(date +%s)-T0 ))s"
