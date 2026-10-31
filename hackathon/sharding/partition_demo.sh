#!/usr/bin/env bash
# P3 partition + recovery demo for the compose.sharded.yaml stack (project aggregatex-sharded).
#
# Fault: the API and writer are detached from the project's net_a only, so shard A is unreachable
# from the router while shard B stays reachable over net_b. Shard A keeps running and accepts local
# writes on its host port. NOTE: one host = one physical failure domain; this is a network
# partition between router and shard, not a host or process failure.
#
# Every expectation is an ASSERTION: the first failure aborts, the network and writer state are
# restored and verified, and the script exits nonzero. Exit 0 + "RESULT: PASS" is the only pass.
#
# usage: sharding/partition_demo.sh [hold_seconds 5..300]   (AX_DRY_RUN=1: preflight only)
# env:   AX_BASE (http://127.0.0.1:8091), AX_DEMO_PASSWORD, AX_DB_SUPERUSER_PASSWORD,
#        AX_MIN_AVAILABLE_MB (1024), AX_A_TIMEOUT_S (10), AX_RECOVERY_TIMEOUT_S (30)
set -Eeuo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=lib_partition.sh
. "$HERE/lib_partition.sh"

HOLD=${1:-20}
[[ "$HOLD" =~ ^[0-9]+$ ]] && [ "$HOLD" -ge 5 ] && [ "$HOLD" -le 300 ] || { echo "ABORT: hold must be an integer 5..300 seconds" >&2; exit 2; }
B=${AX_BASE:-http://127.0.0.1:8091}
MIN_MB=${AX_MIN_AVAILABLE_MB:-1024}
A_TIMEOUT=${AX_A_TIMEOUT_S:-10}
RECOVERY_TIMEOUT=${AX_RECOVERY_TIMEOUT_S:-30}
export PGPASSWORD=${AX_DB_SUPERUSER_PASSWORD:-local-demo-superuser}
PSQL_A=(psql -h 127.0.0.1 -p "${AX_SHARD_A_PORT:-25571}" -U postgres -d aggregatex -XAtq -v ON_ERROR_STOP=1)
PSQL_B=(psql -h 127.0.0.1 -p "${AX_SHARD_B_PORT:-25572}" -U postgres -d aggregatex -XAtq -v ON_ERROR_STOP=1)

AX_STATE_DIR=$(mktemp -d)
JAR="$AX_STATE_DIR/cookies"
BODY="$AX_STATE_DIR/body.json"
RESULTS=${AX_RESULTS_DIR:-$HERE/results}
mkdir -p "$RESULTS"
OUT="$RESULTS/partition-$(date -u +%Y%m%dT%H%M%SZ).txt"
log() { echo "$*" | tee -a "$OUT"; }
fail() { log "ASSERT FAILED: $*"; exit 1; }

# ── cleanup: always restore network + writer state, propagate failures ────────────────────
WRITER=""
cleanup() {
  local rc=$? rrc=0
  trap - EXIT INT TERM HUP
  if [ "${#DETACHED[@]}" -gt 0 ]; then
    restore || restore || rrc=1   # one retry; failures stay listed
  fi
  if [ -n "$WRITER" ]; then restore_writer_state "$WRITER" || { echo "WRITER STATE NOT RESTORED" >&2; rrc=1; }; fi
  if [ "$rrc" -ne 0 ]; then
    echo "RECOVERY FAILED. Still detached: ${DETACHED[*]-none}. Manual fix: docker network connect <captured --alias/--ip args> $AX_NET <container> (state kept in $AX_STATE_DIR)" >&2
    [ "$rc" -eq 0 ] && rc=3
  else
    rm -rf "$AX_STATE_DIR"
  fi
  if [ "${DRY:-0}" = 1 ] && [ "$rc" -eq 0 ]; then log "RESULT: DRY RUN OK (no change made)"
  elif [ "$rc" -eq 0 ]; then log "RESULT: PASS"
  else log "RESULT: FAIL (exit $rc)"; fi
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

# ── HTTP helpers (host-side; cookie auth when login is enabled) ────────────────────────────
req() {  # req METHOD PATH [JSON] -> prints "<status> <ms>", body in $BODY
  # transport errors (timeout, refused) come back as status 000 and fail the assertion
  { curl -s -o "$BODY" -b "$JAR" -X "$1" -H 'content-type: application/json' ${3:+-d "$3"} \
         -w '%{http_code} %{time_total}' --max-time 40 "$B$2" || true; } | awk '{printf "%s %d", $1, $2*1000}'
}
expect() {  # expect STATUS MAX_MS METHOD PATH [JSON]
  local want=$1 max_ms=$2 r code ms; shift 2
  r=$(req "$@"); code=${r%% *}; ms=${r##* }
  log "  $1 $2 -> $code in ${ms}ms (want $want, <= ${max_ms}ms)"
  [ "$code" = "$want" ] || fail "$1 $2 returned $code, expected $want: $(head -c 300 "$BODY")"
  [ "$ms" -le "$max_ms" ] || fail "$1 $2 took ${ms}ms > ${max_ms}ms"
}
body() { python3 -c "import json,sys; d=json.load(open('$BODY')); print($1)"; }
sql_a() { "${PSQL_A[@]}" -c "$1"; }
sql_b() { "${PSQL_B[@]}" -c "$1"; }
oracle_zero() {  # both directions, all three stream tables
  [ "$("$@" -c "select coalesce(sum(missing_in_st + extra_in_st), -1) from ax.oracle_mismatches()")" = 0 ]
}

# ── 0. preflight (no mutation) ─────────────────────────────────────────────────────────────
log "# partition demo $(date -u +%FT%TZ) hold=${HOLD}s project=$AX_PROJECT network=$AX_NET"
for cmd in docker curl psql python3; do command -v "$cmd" >/dev/null || fail "missing command: $cmd"; done
docker info >/dev/null 2>&1 || fail "Docker daemon not reachable; nothing was changed"
avail=$(available_mb)
[ "$avail" -ge "$MIN_MB" ] || fail "host memory gate: ${avail} MiB available < ${MIN_MB} MiB (AX_MIN_AVAILABLE_MB)"
API=$(container_for api); WRITER_C=$(container_for writer); SHA=$(container_for shard_a); SHB=$(container_for shard_b)
check_network_ownership
check_network_members "$(printf '%s\n' "$API" "$WRITER_C" "$SHA" | sort | tr '\n' ' ' | sed 's/ $//')"
! attached_to "$SHB" "$AX_NET" || fail "shard B ($SHB) is attached to $AX_NET"
attached_to "$API" "$AX_NET_B" || fail "API has no route to shard B ($AX_NET_B)"
attached_to "$WRITER_C" "$AX_NET_B" || fail "writer has no route to shard B ($AX_NET_B)"
for c in "$API" "$SHA" "$SHB"; do [ "$(docker inspect "$c" -f '{{.State.Running}}')" = true ] || fail "$c is not running"; done
log "preflight OK: containers $API $WRITER_C $SHA $SHB; ${avail} MiB available; $AX_NET members verified"
if [ "${AX_DRY_RUN:-0}" = 1 ]; then DRY=1; exit 0; fi

remember_writer_state "$WRITER_C"; WRITER=$WRITER_C
log "writer initially running: $WRITER_WAS_RUNNING"

if [ "$(req GET /api/auth/me | cut -d' ' -f1)" = 401 ]; then
  log "login enabled: signing in as operator"
  curl -s -c "$JAR" -o /dev/null -X POST "$B/api/auth/login" -H 'content-type: application/json' \
       -d "{\"email\":\"admin@demo.local\",\"password\":\"${AX_DEMO_PASSWORD:-demo1234}\"}"
fi

log "## 0. baseline"
expect 200 5000 GET /api/tenants/1/summary
expect 200 5000 GET /api/tenants/2/summary
expect 200 5000 GET /api/shards
[ "$(body "d['complete']")" = True ] || fail "/api/shards not complete before the fault"
A_ROWS0=$(sql_a "select count(*) from ax.orders")
B_ROWS0=$(sql_b "select count(*) from ax.orders")
log "  shard A rows=$A_ROWS0 shard B rows=$B_ROWS0"

# ── 1. partition ───────────────────────────────────────────────────────────────────────────
log "## 1. partition: detach $API and $WRITER_C from $AX_NET"
detach "$API"
detach "$WRITER_C"
T0=$(date +%s)
MAX_A_MS=$((A_TIMEOUT * 1000))
expect 503 "$MAX_A_MS" GET /api/tenants/1/summary
[ "$(body "d.get('shard')")" = a ] || fail "503 body does not name shard a"
expect 503 "$MAX_A_MS" GET /api/tenants/3/top-products
expect 503 "$MAX_A_MS" POST /api/tenants/1/live-write '{"action":"insert"}'
[ "$(sql_a "select count(*) from ax.orders")" = "$A_ROWS0" ] || fail "phantom write: shard A row count changed after a 503 write"
expect 200 5000 GET /api/tenants/2/summary
expect 200 5000 GET /api/tenants/5/trends
expect 200 40000 POST /api/tenants/2/live-write '{"action":"insert"}'
[ "$(body "d.get('committed') is True and d.get('shard')=='b' and d.get('lag_ms') is not None")" = True ] \
  || fail "shard B write not committed or not visible: $(head -c 300 "$BODY")"
B_ORDER=$(body "d['order_id']")
[ "$(sql_b "select count(*) from ax.orders where tenant_id=2 and order_id=$B_ORDER")" = 1 ] || fail "B write not on shard B"
[ "$(sql_a "select count(*) from ax.orders where order_id=$B_ORDER")" = 0 ] || fail "B write leaked to shard A"
expect 200 "$MAX_A_MS" GET /api/shards
[ "$(body "(d['complete'], d['missing_shards'], d['total_orders'] is None, d['partial_total_orders'] is not None)")" = "(False, ['a'], True, True)" ] \
  || fail "/api/shards does not report an explicit partial view: $(head -c 300 "$BODY")"
expect 200 "$MAX_A_MS" GET /api/health
[ "$(body "d['status']")" = degraded ] || fail "/api/health not degraded"

sql_a "insert into ax.orders (tenant_id, order_id, customer_id, product_id, status, quantity, unit_price_cents, created_at)
       select 1, nextval('ax.order_id_seq'), 1 + (g % 1000), 1 + (g % 200), 'paid', 1, 1500, now() from generate_series(1, 25) g" >/dev/null
[ "$(sql_a "select count(*) from ax.orders")" = $((A_ROWS0 + 25)) ] || fail "shard A local insert count mismatch"
log "  25 local inserts on shard A during the partition"
sleep "$HOLD"
expect 503 "$MAX_A_MS" GET /api/tenants/1/summary

# ── 2. restore ─────────────────────────────────────────────────────────────────────────────
log "## 2. restore"
restore || fail "network restore failed"
TR=$(date +%s)
ok=0
for _ in $(seq 1 $((RECOVERY_TIMEOUT * 2))); do
  [ "$(req GET /api/tenants/1/summary | cut -d' ' -f1)" = 200 ] && { ok=1; break; }; sleep 0.5
done
[ "$ok" = 1 ] || fail "tenant 1 not served within ${RECOVERY_TIMEOUT}s of restore"
log "  tenant 1 served again $(( $(date +%s) - TR ))s after restore; partition lasted $(( TR - T0 ))s"
expect 200 5000 GET /api/shards
[ "$(body "d['complete']")" = True ] || fail "/api/shards still partial after restore"

# ── 3. catch-up + oracle on BOTH shards (writes quiesced) ─────────────────────────────────
log "## 3. oracle (writer quiesced)"
if [ "$(docker inspect "$WRITER_C" -f '{{.State.Running}}')" = true ]; then docker stop "$WRITER_C" >/dev/null; fi
ok=0
for _ in $(seq 1 30); do
  if oracle_zero "${PSQL_A[@]}" && oracle_zero "${PSQL_B[@]}"; then ok=1; break; fi; sleep 2
done
[ "$ok" = 1 ] || fail "oracle not 0/0 on both shards within 60s (A: $(sql_a "select string_agg(missing_in_st||'/'||extra_in_st, ' ') from ax.oracle_mismatches()"); B: $(sql_b "select string_agg(missing_in_st||'/'||extra_in_st, ' ') from ax.oracle_mismatches()"))"
log "  oracle 0/0 on shard A and shard B"
FROM=$(python3 -c 'import datetime as d; print((d.datetime.now(d.timezone.utc)-d.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ"))')
expect 200 5000 GET "/api/tenants/1/summary?from=$FROM"
API_ORD=$(body "d['summary']['orders']")
SQL_ORD=$(sql_a "select count(*) from ax.orders where tenant_id=1 and created_at >= '$FROM'")
[ "$API_ORD" = "$SQL_ORD" ] || fail "tenant 1 last-10-min orders API=$API_ORD SQL=$SQL_ORD"
log "  tenant 1 last 10 min: API=$API_ORD SQL=$SQL_ORD (includes partition-time local inserts)"
exit 0   # cleanup restores the writer's original state and prints RESULT
