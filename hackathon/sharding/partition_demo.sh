#!/usr/bin/env bash
# P3 partition + recovery demo. Touches ONLY the demo-owned Docker network aggregatex-sharded_net_a:
# the API and writer are detached from it (shard A unreachable from the router), then re-attached.
# Shard A itself keeps running and still accepts local writes on its host port during the partition.
# Requires: compose.sharded.yaml stack up. Works with login on (uses admin) or off.
# usage: sharding/partition_demo.sh [hold_seconds]   -> sharding/results/partition-<ts>.txt
set -uo pipefail
HOLD=${1:-20}
B=${AX_BASE:-http://127.0.0.1:8091}
NET=aggregatex-sharded_net_a
API=aggregatex-sharded-api-1
WRITER=aggregatex-sharded-writer-1
export PGPASSWORD=${AX_DB_SUPERUSER_PASSWORD:-local-demo-superuser}
PSQL_A="psql -h 127.0.0.1 -p 25571 -U postgres -d aggregatex -XAtq"
HERE=$(cd "$(dirname "$0")" && pwd)
OUT="$HERE/results/partition-$(date -u +%Y%m%dT%H%M%SZ).txt"
JAR=$(mktemp)
mkdir -p "$HERE/results"
docker info >/dev/null 2>&1 || { echo "ABORT: Docker daemon not reachable; nothing was changed"; exit 2; }
for c in "$API" "$WRITER" aggregatex-sharded-shard_a-1 aggregatex-sharded-shard_b-1; do
  docker inspect "$c" >/dev/null 2>&1 || { echo "ABORT: container $c not found; nothing was changed"; exit 2; }
done
attached() { docker inspect -f "{{json .NetworkSettings.Networks}}" "$1" | grep -q "\"$NET\""; }
# Safety: shard B must NOT be on the network we cut, and the API must have another route (net_b).
docker inspect -f '{{json .NetworkSettings.Networks}}' aggregatex-sharded-shard_b-1 | grep -q "\"$NET\"" && { echo "ABORT: shard B is attached to $NET"; exit 2; }
docker inspect -f '{{json .NetworkSettings.Networks}}' "$API" | grep -q '"aggregatex-sharded_net_b"' || { echo "ABORT: API has no route to shard B"; exit 2; }
DETACHED=()
restore() {  # re-attach only what we detached; report (never swallow) failures
  local rc=0
  for c in "${DETACHED[@]}"; do
    attached "$c" || docker network connect "$NET" "$c" || { echo "RESTORE FAILED for $c on $NET" >&2; rc=1; }
    attached "$c" || { echo "RESTORE NOT VERIFIED for $c" >&2; rc=1; }
  done
  DETACHED=(); return $rc
}
trap 'restore; rm -f "$JAR"' EXIT

log() { echo "$*" | tee -a "$OUT"; }
req() {  # method path [json] -> "<code> <ms>"
  local m=$1 p=$2 d=${3:-}
  curl -s -o /tmp/ax_body.$$ -b "$JAR" -X "$m" -H 'content-type: application/json' ${d:+-d "$d"} \
       -w '%{http_code} %{time_total}' --max-time 30 "$B$p" | awk '{printf "%s %.0fms", $1, $2*1000}'
}
body() { head -c "${1:-300}" /tmp/ax_body.$$; echo; }

curl -s -c "$JAR" -o /dev/null -X POST "$B/api/auth/login" -H 'content-type: application/json' \
     -d "{\"email\":\"admin@demo.local\",\"password\":\"${AX_DEMO_PASSWORD:-demo1234}\"}"
docker start "$WRITER" >/dev/null 2>&1

log "# partition demo $(date -u +%FT%TZ)  hold=${HOLD}s  network=$NET"
log "## 0. before"
log "tenant 1 (A) summary: $(req GET /api/tenants/1/summary)"
log "tenant 2 (B) summary: $(req GET /api/tenants/2/summary)"
A_ROWS0=$($PSQL_A -c "select count(*) from ax.orders")
log "shard A rows: $A_ROWS0"

log "## 1. partition: detach $API and $WRITER from $NET"
docker network disconnect "$NET" "$API" && DETACHED+=("$API")
docker network disconnect "$NET" "$WRITER" && DETACHED+=("$WRITER")
T0=$(date +%s)
for i in 1 2 3; do
  log "tenant 1 (A) summary #$i: $(req GET /api/tenants/1/summary)"; [ $i = 1 ] && log "  body: $(body 260)"
done
log "tenant 3 (A) top-products: $(req GET /api/tenants/3/top-products)"
log "tenant 2 (B) summary: $(req GET /api/tenants/2/summary)"
log "tenant 5 (B) trends: $(req GET /api/tenants/5/trends)"
log "tenant 1 (A) live-write insert: $(req POST /api/tenants/1/live-write '{"action":"insert"}')"; log "  body: $(body 200)"
log "tenant 2 (B) live-write insert: $(req POST /api/tenants/2/live-write '{"action":"insert"}')"; log "  body: $(body 220)"
log "/api/health: $(req GET /api/health)"; log "  body: $(body 220)"
log "/api/shards: $(req GET /api/shards)"
python3 -c "import json;d=json.load(open('/tmp/ax_body.$$'));print('  complete=%s missing=%s total=%s partial_total=%s'%(d['complete'],d['missing_shards'],d['total_orders'],d['partial_total_orders']))" | tee -a "$OUT"

# Local activity on shard A while it is cut off from the router (its own app keeps writing).
$PSQL_A -c "insert into ax.orders (tenant_id, order_id, customer_id, product_id, status, quantity, unit_price_cents, created_at)
            select 1, nextval('ax.order_id_seq'), 1 + (g % 1000), 1 + (g % 200), 'paid', 1, 1500, now() from generate_series(1, 25) g"
A_ROWS1=$($PSQL_A -c "select count(*) from ax.orders")
log "shard A rows after router-side write attempt + 25 LOCAL inserts: $A_ROWS1 (expected $((A_ROWS0 + 25)): no phantom write from the router)"
sleep "$HOLD"
log "tenant 1 (A) summary after ${HOLD}s: $(req GET /api/tenants/1/summary)"
log "writer log during partition: $(docker logs --since "$(( $(date +%s) - T0 + 5 ))s" "$WRITER" 2>&1 | grep 'writer stats' | tail -1)"

log "## 2. restore: re-attach to $NET"
restore || { log "RECOVERY FAILED: network not restored"; exit 1; }
TR=$(date +%s)
for i in $(seq 1 40); do
  r=$(req GET /api/tenants/1/summary); [ "${r%% *}" = 200 ] && break; sleep 0.5
done
log "tenant 1 (A) summary after restore: $r  (recovered within $(( $(date +%s) - TR ))s)"
[ "${r%% *}" = 200 ] || { log "RECOVERY FAILED: tenant 1 still not served"; exit 1; }
req GET /api/shards >/dev/null; python3 -c "import json,sys;d=json.load(open('/tmp/ax_body.$$'));sys.exit(0 if d['complete'] else 1)" \
  && log "/api/shards complete=true after restore" || { log "RECOVERY FAILED: /api/shards still partial"; exit 1; }
log "partition duration: $(( TR - T0 ))s"

log "## 3. catch-up + oracle (writer paused)"
docker stop "$WRITER" >/dev/null
sleep 6
log "shard A oracle: $($PSQL_A -c "select string_agg(stream_table||'='||missing_in_st||'/'||extra_in_st, ' ') from ax.oracle_mismatches()")"
log "shard A refreshes since restore: $($PSQL_A -c "select string_agg(action||':'||n, ' ') from (select h.action, count(*) n from pgtrickle.pgt_refresh_history h where h.start_time > to_timestamp($TR) group by 1) x")"
API_ORD=$(curl -s -b "$JAR" "$B/api/tenants/1/summary?from=$(date -u -v-10M +%FT%TZ 2>/dev/null || date -u -d '-10 min' +%FT%TZ)" | python3 -c 'import json,sys;print(json.load(sys.stdin)["summary"]["orders"])')
SQL_ORD=$($PSQL_A -c "select count(*) from ax.orders where tenant_id=1 and created_at >= now() - interval '10 minutes'")
log "tenant 1 orders in last 10 min: API=$API_ORD SQL=$SQL_ORD (includes the 25 local partition-time inserts)"
docker start "$WRITER" >/dev/null
log "# done -> $OUT"
