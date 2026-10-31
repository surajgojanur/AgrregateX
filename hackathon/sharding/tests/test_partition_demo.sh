#!/usr/bin/env bash
# End-to-end test of partition_demo.sh against fake docker/curl/psql (no Docker, no network).
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin"
for n in docker:fake_docker curl:fake_http psql:fake_psql; do
  printf '#!/bin/sh\nexec python3 "%s/%s.py" "$@"\n' "$HERE" "${n#*:}" > "$T/bin/${n%%:*}"; chmod +x "$T/bin/${n%%:*}"
done
export PATH="$T/bin:$PATH" FAKE_DOCKER_STATE="$T/state.json" FAKE_DOCKER_LOG="$T/calls.log" FAKE_PSQL_STATE="$T/psql.json"
export AX_MIN_AVAILABLE_MB=0 AX_RESULTS_DIR="$T/results"   # never write fake runs into real evidence
pass=0; failn=0
ok() { echo "PASS $1"; pass=$((pass+1)); }
ko() { echo "FAIL $1"; failn=$((failn+1)); }
reset() {
  rm -f "$FAKE_PSQL_STATE"; : > "$FAKE_DOCKER_LOG"
  cat > "$FAKE_DOCKER_STATE" <<JSON
{"networks": {"aggregatex-sharded_net_a": {"project": "aggregatex-sharded", "name": "net_a"}},
 "containers": {
  "ax-api": {"project": "aggregatex-sharded", "service": "api", "running": true, "networks": {
     "aggregatex-sharded_net_a": {"Aliases": ["ax-api", "api"], "IPAMConfig": {"IPv4Address": "172.30.0.10"}},
     "aggregatex-sharded_net_b": {"Aliases": ["api"], "IPAMConfig": null}}},
  "ax-writer": {"project": "aggregatex-sharded", "service": "writer", "running": $1, "networks": {
     "aggregatex-sharded_net_a": {"Aliases": ["writer"], "IPAMConfig": null},
     "aggregatex-sharded_net_b": {"Aliases": ["writer"], "IPAMConfig": null}}},
  "ax-a": {"project": "aggregatex-sharded", "service": "shard_a", "running": true, "networks": {
     "aggregatex-sharded_net_a": {"Aliases": ["shard_a"], "IPAMConfig": null}}},
  "ax-b": {"project": "aggregatex-sharded", "service": "shard_b", "running": true, "networks": {
     "aggregatex-sharded_net_b": {"Aliases": ["shard_b"], "IPAMConfig": null}}}}}
JSON
}
restored() { python3 -c "
import json; c=json.load(open('$FAKE_DOCKER_STATE'))['containers']
e=c['ax-api']['networks'].get('aggregatex-sharded_net_a') or {}
assert sorted(e.get('Aliases') or [])==['api','ax-api'] and (e.get('IPAMConfig') or {}).get('IPv4Address')=='172.30.0.10', e
assert 'aggregatex-sharded_net_a' in c['ax-writer']['networks']
assert c['ax-writer']['running'] == $1, c['ax-writer']['running']"; }

reset true
out=$(bash "$HERE/../partition_demo.sh" 5 2>&1); rc=$?
[ $rc -eq 0 ] && [[ "$out" == *"RESULT: PASS"* ]] && restored True && ok "happy path PASS, exact restore, writer back to RUNNING" || ko "happy path rc=$rc: $(echo "$out" | tail -4)"

reset false
out=$(bash "$HERE/../partition_demo.sh" 5 2>&1); rc=$?
[ $rc -eq 0 ] && restored False && ok "writer initially STOPPED stays STOPPED" || ko "writer stopped rc=$rc: $(echo "$out" | tail -3)"

reset true
out=$(BUG_A_200=1 bash "$HERE/../partition_demo.sh" 5 2>&1); rc=$?
[ $rc -eq 1 ] && [[ "$out" == *"ASSERT FAILED"*"returned 200, expected 503"* ]] && [[ "$out" == *"RESULT: FAIL"* ]] && restored True \
  && ok "fail-open shard A answer is caught; exit 1; network still restored" || ko "assert propagation rc=$rc: $(echo "$out" | tail -3)"

reset true
out=$(BUG_A_200=1 FAIL_CONNECT=1 bash "$HERE/../partition_demo.sh" 5 2>&1); rc=$?
[ $rc -ne 0 ] && [[ "$out" == *"RECOVERY FAILED"* ]] && [[ "$out" == *"RESULT: FAIL"* ]] \
  && ok "assertion + failed restore: nonzero exit, RECOVERY FAILED reported (not masked)" || ko "restore failure masking rc=$rc: $(echo "$out" | tail -3)"

reset true
out=$(bash "$HERE/../partition_demo.sh" 4 2>&1); rc=$?
[ $rc -eq 2 ] && ! grep -q "network disconnect" "$FAKE_DOCKER_LOG" && ok "invalid hold rejected before any change" || ko "hold validation rc=$rc"

reset true
out=$(AX_MIN_AVAILABLE_MB=99999999 bash "$HERE/../partition_demo.sh" 5 2>&1); rc=$?
[ $rc -ne 0 ] && [[ "$out" == *"memory gate"* ]] && ! grep -q "network disconnect" "$FAKE_DOCKER_LOG" && ok "memory gate aborts before any change" || ko "memory gate rc=$rc"

reset true
out=$(AX_DRY_RUN=1 bash "$HERE/../partition_demo.sh" 5 2>&1); rc=$?
[ $rc -eq 0 ] && [[ "$out" == *"DRY RUN OK"* ]] && ! grep -q "network disconnect" "$FAKE_DOCKER_LOG" && ok "dry run: preflight only, no mutation" || ko "dry run rc=$rc"

echo "passed=$pass failed=$failn"
[ "$failn" -eq 0 ]
