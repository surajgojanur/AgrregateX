#!/usr/bin/env bash
# Isolate only shard A by detaching A from its dedicated api<->A test network.
# Requires API to remain attached to a separate B network; no tests are run here.
set -Eeuo pipefail
if [[ $# -ne 8 ]]; then
  echo "usage: SHARD_B_TOKEN=... SHARD_B_WRITE_JSON=... $0 <dedicated-a-test-network> <api-container> <shard-a-container> <shard-b-container> <b-read-url> <b-write-url> <a-health-url> <seconds>" >&2; exit 64
fi
: "${SHARD_B_TOKEN:?bearer token for disposable B test tenant required}"
: "${SHARD_B_WRITE_JSON:?safe test mutation JSON required}"
network=$1 api=$2 shard_a=$3 shard_b=$4 b_read_url=$5 b_write_url=$6 a_url=$7 seconds=$8
[[ $seconds =~ ^[1-9][0-9]?$ ]] || { echo 'duration must be 1..99 seconds' >&2; exit 64; }
case "$network" in *shard-a*test*|*test*shard-a*|*disposable*shard-a*|*shard-a*disposable*) ;; *) echo 'network must be explicitly named shard-a test/disposable network' >&2; exit 65;; esac
for c in "$api" "$shard_a" "$shard_b"; do docker inspect "$c" >/dev/null; done
# Snapshot API and shard network attachment metadata before changing anything.
api_json=$(docker inspect "$api")
shard_json=$(docker inspect "$shard_a")
readarray -t api_nets < <(python3 -c 'import json,sys; d=json.loads(sys.argv[1])[0]; print("\n".join(d["NetworkSettings"]["Networks"].keys()))' "$api_json")
readarray -t a_nets < <(python3 -c 'import json,sys; d=json.loads(sys.argv[1])[0]; print("\n".join(d["NetworkSettings"]["Networks"].keys()))' "$shard_json")
b_json=$(docker inspect "$shard_b")
readarray -t b_nets < <(python3 -c 'import json,sys; d=json.loads(sys.argv[1])[0]; print("\n".join(d["NetworkSettings"]["Networks"].keys()))' "$b_json")
[[ " ${api_nets[*]} " == *" $network "* && " ${a_nets[*]} " == *" $network "* ]] || { echo 'API and shard A must both attach to target network' >&2; exit 66; }
python3 - "$network" "${api_nets[*]}" "${a_nets[*]}" "${b_nets[*]}" <<'PYCHECK'
import sys
from pathlib import Path
sys.path.insert(0, 'hackathon/benchmark/sharding')
from network_safety import validate_isolated_target
validate_isolated_target(sys.argv[1], sys.argv[2].split(), sys.argv[3].split(), sys.argv[4].split())
PYCHECK
probe_b_read() { docker exec "$api" curl -fsS --max-time 3 -H "Authorization: Bearer $SHARD_B_TOKEN" "$b_read_url" >/dev/null; }
probe_b_write() { docker exec "$api" curl -fsS --max-time 3 -X POST -H "Authorization: Bearer $SHARD_B_TOKEN" -H 'Content-Type: application/json' --data "$SHARD_B_WRITE_JSON" "$b_write_url" >/dev/null; }
probe_b_read && probe_b_write || { echo 'shard B read/write preflight failed; refusing partition' >&2; exit 68; }
# Capture only the attachment fields needed to restore the detached container.
attachment=$(docker network inspect "$network")
config=$(python3 - "$shard_json" "$network" "$attachment" <<'PY'
import json,sys
container=json.loads(sys.argv[1])[0]['NetworkSettings']['Networks'][sys.argv[2]]
net=json.loads(sys.argv[3])[0]
aliases=[a for a in container.get('Aliases',[]) if a and a != container.get('NetworkID')]
out={'aliases':aliases}
for key in ('IPv4Address','IPv6Address'):
    value=container.get(key,'').split('/')[0]
    if value: out[key]=value
print(json.dumps(out))
PY
)
restore() {
  local rc=0
  mapfile -t restore_args < <(python3 - "$config" <<'PYCFG'
import json,sys
sys.path.insert(0, 'hackathon/benchmark/sharding')
from network_safety import attachment_restore_options
for arg in attachment_restore_options(json.loads(sys.argv[1])): print(arg)
PYCFG
)
  if ! docker network connect "${restore_args[@]}" "$network" "$shard_a"; then
    # Already attached is okay only if subsequent API health probes confirm reachability.
    docker inspect "$shard_a" >/dev/null 2>&1 || rc=1
  fi
  if ! docker network inspect "$network" >/dev/null 2>&1; then rc=1; fi
  actual=$(docker inspect "$shard_a" 2>/dev/null || true)
  if ! python3 - "$actual" "$network" "$config" <<'PYVERIFY'
import json,sys
try:
 actual=json.loads(sys.argv[1])[0]['NetworkSettings']['Networks'][sys.argv[2]]
 expected=json.loads(sys.argv[3])
 aliases=set(actual.get('Aliases',[]))
 if not set(expected['aliases']).issubset(aliases): raise SystemExit(1)
 for key in ('IPv4Address','IPv6Address'):
  if expected.get(key) and actual.get(key,'').split('/')[0] != expected[key]: raise SystemExit(1)
except (ValueError,KeyError,IndexError):
 raise SystemExit(1)
PYVERIFY
  then rc=1; fi
  if ! docker exec "$api" sh -lc "curl -fsS --max-time 3 '$a_url' >/dev/null"; then rc=1; fi
  if ! probe_b_read || ! probe_b_write; then rc=1; fi
  return "$rc"
}
cleanup() {
  local status=$?
  trap - EXIT INT TERM HUP
  if ! restore; then echo 'ERROR: shard A/B connectivity restoration could not be verified' >&2; status=1; fi
  exit "$status"
}
trap cleanup EXIT INT TERM HUP
docker network disconnect "$network" "$shard_a"
echo "PARTITION ACTIVE: only shard A detached from $network; B path preserved"
probe_b_read && probe_b_write || { echo 'B read/write failed during A partition' >&2; exit 69; }
if docker exec "$api" sh -lc "curl -fsS --max-time 2 '$a_url' >/dev/null"; then echo 'A unexpectedly reachable during partition' >&2; exit 70; fi
read -r -t "$seconds" -p "A isolated; press Enter to restore, auto restore in ${seconds}s: " _ || true
# EXIT cleanup performs and verifies restoration. No SIGKILL/power-loss guarantee.
