#!/usr/bin/env bash
# Unit tests for sharding/lib_partition.sh against a fake docker (no Docker daemon needed).
# usage: bash sharding/tests/test_lib_partition.sh   -> exit 0 when all pass
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin"; printf '#!/bin/sh\nexec python3 "%s/fake_docker.py" "$@"\n' "$HERE" > "$T/bin/docker"; chmod +x "$T/bin/docker"
export PATH="$T/bin:$PATH" FAKE_DOCKER_STATE="$T/state.json" FAKE_DOCKER_LOG="$T/calls.log"
pass=0; failn=0
ok() { echo "PASS $1"; pass=$((pass+1)); }
ko() { echo "FAIL $1"; failn=$((failn+1)); }
reset_state() {
  cat > "$FAKE_DOCKER_STATE" <<JSON
{"networks": {"aggregatex-sharded_net_a": {"project": "aggregatex-sharded", "name": "net_a"},
              "aggregatex-sharded_net_b": {"project": "aggregatex-sharded", "name": "net_b"}},
 "containers": {
  "ax-api": {"project": "aggregatex-sharded", "service": "api", "running": true, "networks": {
     "aggregatex-sharded_net_a": {"Aliases": ["ax-api", "api", "router"], "IPAMConfig": {"IPv4Address": "172.30.0.10"}},
     "aggregatex-sharded_net_b": {"Aliases": ["api"], "IPAMConfig": null}}},
  "ax-writer": {"project": "aggregatex-sharded", "service": "writer", "running": false, "networks": {
     "aggregatex-sharded_net_a": {"Aliases": ["ax-writer", "writer"], "IPAMConfig": null},
     "aggregatex-sharded_net_b": {"Aliases": ["writer"], "IPAMConfig": null}}},
  "ax-a": {"project": "aggregatex-sharded", "service": "shard_a", "running": true, "networks": {
     "aggregatex-sharded_net_a": {"Aliases": ["shard_a"], "IPAMConfig": null}}},
  "ax-b": {"project": "aggregatex-sharded", "service": "shard_b", "running": true, "networks": {
     "aggregatex-sharded_net_b": {"Aliases": ["shard_b"], "IPAMConfig": null}}},
  "stranger": {"project": "other", "service": "api", "running": true, "networks": {}}}}
JSON
  : > "$FAKE_DOCKER_LOG"
}
run() {  # run a snippet in a fresh shell that sources the library
  AX_STATE_DIR="$T/st" bash -c "set -Eeuo pipefail; mkdir -p \"\$AX_STATE_DIR\"; . '$HERE/../lib_partition.sh'; $1"
}

reset_state
out=$(run 'detach ax-api; detach ax-writer; restore; echo LEFT=${#DETACHED[@]}') && [ "${out##*LEFT=}" = 0 ] \
  && python3 -c "
import json; c=json.load(open('$FAKE_DOCKER_STATE'))['containers']
e=c['ax-api']['networks']['aggregatex-sharded_net_a']
assert sorted(e['Aliases'])==['api','ax-api','router'] and e['IPAMConfig']=={'IPv4Address':'172.30.0.10'}, e
assert 'aggregatex-sharded_net_a' in c['ax-writer']['networks']" \
  && grep -q -- '--alias router.*--ip 172.30.0.10 aggregatex-sharded_net_a ax-api' "$FAKE_DOCKER_LOG" \
  && ok "detach+restore recreates exact aliases and static IP" || ko "detach+restore exact"

reset_state
out=$(FAIL_CONNECT=1 run 'detach ax-api; if restore; then echo RC=0; else echo RC=1; fi; echo LEFT=${DETACHED[*]-}' 2>&1)
case "$out" in *"RESTORE FAILED"*RC=1*LEFT=ax-api*) ok "failed reconnect propagates nonzero and keeps container listed";; *) ko "failed reconnect: $out";; esac

reset_state
out=$(DROP_ALIAS=router run 'detach ax-api; if restore; then echo RC=0; else echo RC=1; fi' 2>&1)
case "$out" in *"NOT VERIFIED"*RC=1*) ok "restore that loses an alias is detected";; *) ko "alias loss: $out";; esac

reset_state
out=$(FAIL_DISCONNECT=1 run 'detach ax-api; echo SHOULD-NOT-REACH' 2>&1) ; rc=$?
[ $rc -ne 0 ] && [[ "$out" != *SHOULD-NOT-REACH* ]] && ok "failed disconnect aborts" || ko "failed disconnect: rc=$rc $out"

reset_state
run 'remember_writer_state ax-writer; docker start ax-writer >/dev/null; restore_writer_state ax-writer' \
  && [ "$(docker inspect ax-writer -f '{{.State.Running}}')" = false ] && ok "writer returned to original STOPPED state" || ko "writer stopped state"
reset_state
python3 -c "import json;p='$FAKE_DOCKER_STATE';d=json.load(open(p));d['containers']['ax-writer']['running']=True;json.dump(d,open(p,'w'))"
run 'remember_writer_state ax-writer; docker stop ax-writer >/dev/null; restore_writer_state ax-writer' \
  && [ "$(docker inspect ax-writer -f '{{.State.Running}}')" = true ] && ok "writer returned to original RUNNING state" || ko "writer running state"

reset_state
run 'check_network_ownership; check_network_members "ax-a ax-api ax-writer"' >/dev/null 2>&1 && ok "ownership labels + exact member set accepted" || ko "ownership ok case"
run 'AX_NET=aggregatex-sharded_net_b; check_network_ownership' >/dev/null 2>&1 && ko "net_b accepted as fault network" || ok "rejects a network that is not the project's net_a"
run 'check_network_members "ax-api ax-writer"' >/dev/null 2>&1 && ko "unexpected member accepted" || ok "rejects unexpected containers on the fault network"
run 'AX_PROJECT=other; container_for shard_a' >/dev/null 2>&1 && ko "foreign project accepted" || ok "container lookup is scoped to the Compose project"
[ "$(run 'container_for api')" = ax-api ] && ok "container lookup ignores same-service containers of other projects" || ko "lookup scoping"

echo "passed=$pass failed=$failn"
[ "$failn" -eq 0 ]
