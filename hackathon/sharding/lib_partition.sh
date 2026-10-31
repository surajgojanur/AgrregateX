# shellcheck shell=bash
# Library for sharding/partition_demo.sh. Sourced, never executed. Every function returns
# nonzero on failure; callers run under `set -Eeuo pipefail`.
#
# Safety model (PR #22 review, Codex audit on #12):
#   * only containers and the network carrying Compose labels of $AX_PROJECT are touched;
#   * the fault network must contain exactly {api, writer, shard_a}; shard B must not be on it;
#   * every endpoint's aliases and static IPv4/IPv6 are captured BEFORE disconnect and
#     restored exactly; restore is verified and failures are reported, never swallowed;
#   * the writer's original running/stopped state is restored.

AX_PROJECT=${AX_PROJECT:-aggregatex-sharded}
AX_NET=${AX_NET:-${AX_PROJECT}_net_a}
AX_NET_B=${AX_NET_B:-${AX_PROJECT}_net_b}
AX_STATE_DIR=${AX_STATE_DIR:-}
DETACHED=()          # containers currently detached from $AX_NET by us
WRITER_WAS_RUNNING=""

die() { echo "ABORT: $*" >&2; return 1; }

_json_get() {  # python3 -c field extraction from stdin JSON: _json_get 'expr'
  python3 -c "import json,sys; d=json.load(sys.stdin); v=($1); print(v if not isinstance(v,(dict,list)) else json.dumps(v))"
}

# Resolve exactly one container of the project by Compose service label.
container_for() {
  local svc=$1 ids n
  ids=$(docker ps -a --filter "label=com.docker.compose.project=$AX_PROJECT" \
                     --filter "label=com.docker.compose.service=$svc" --format '{{.Names}}')
  n=$(printf '%s\n' "$ids" | grep -c . || true)
  [ "$n" = 1 ] || die "expected exactly 1 '$svc' container in project $AX_PROJECT, found $n" || return 1
  printf '%s' "$ids"
}

# Network must exist, belong to the project (Compose labels) and be the net_a network.
check_network_ownership() {
  local proj netlbl
  proj=$(docker network inspect "$AX_NET" -f '{{index .Labels "com.docker.compose.project"}}' 2>/dev/null) \
    || die "network $AX_NET not found" || return 1
  netlbl=$(docker network inspect "$AX_NET" -f '{{index .Labels "com.docker.compose.network"}}')
  [ "$proj" = "$AX_PROJECT" ] || die "network $AX_NET is not owned by Compose project $AX_PROJECT (label: '$proj')" || return 1
  [ "$netlbl" = "net_a" ] || die "network $AX_NET is not the project's net_a (label: '$netlbl')" || return 1
}

# Members of $AX_NET must be exactly the expected set (no unrelated containers in the blast radius).
check_network_members() {
  local expected=$1 actual   # expected: space-separated sorted names
  actual=$(docker network inspect "$AX_NET" -f '{{range .Containers}}{{.Name}} {{end}}' | tr ' ' '\n' | grep . | sort | tr '\n' ' ' | sed 's/ $//')
  [ "$actual" = "$expected" ] || die "$AX_NET members are '$actual', expected '$expected'" || return 1
}

attached_to() {  # attached_to <container> <network>
  docker inspect "$1" -f '{{json .NetworkSettings.Networks}}' | python3 -c "import json,sys; sys.exit(0 if '$2' in json.load(sys.stdin) else 1)"
}

# Save the endpoint config (aliases, static IPs) of <container> on $AX_NET to the state dir.
capture_endpoint() {
  local c=$1
  [ -n "$AX_STATE_DIR" ] || die "AX_STATE_DIR not set" || return 1
  docker inspect "$c" -f "{{json (index .NetworkSettings.Networks \"$AX_NET\")}}" > "$AX_STATE_DIR/$c.endpoint.json"
  python3 - "$AX_STATE_DIR/$c.endpoint.json" <<'PY' || die "could not capture endpoint of $c on $AX_NET" || return 1
import json, sys
d = json.load(open(sys.argv[1]))
assert isinstance(d, dict) and d, "container is not attached"
PY
}

# Build `docker network connect` args that recreate the captured endpoint.
connect_args() {
  python3 - "$AX_STATE_DIR/$1.endpoint.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
args = []
for a in sorted(set(d.get("Aliases") or [])):
    args += ["--alias", a]
ipam = d.get("IPAMConfig") or {}
if ipam.get("IPv4Address"):
    args += ["--ip", ipam["IPv4Address"]]
if ipam.get("IPv6Address"):
    args += ["--ip6", ipam["IPv6Address"]]
print("\n".join(args))
PY
}

# Verify the live endpoint matches the captured one (aliases superset, identical static IPs).
verify_endpoint() {
  local c=$1 now
  now=$(docker inspect "$c" -f "{{json (index .NetworkSettings.Networks \"$AX_NET\")}}")
  python3 - "$AX_STATE_DIR/$c.endpoint.json" "$now" <<'PY'
import json, sys
want = json.load(open(sys.argv[1])); got = json.loads(sys.argv[2] or "null")
if not got:
    sys.exit("not attached")
missing = set(want.get("Aliases") or []) - set(got.get("Aliases") or [])
wi, gi = want.get("IPAMConfig") or {}, got.get("IPAMConfig") or {}
bad = [k for k in ("IPv4Address", "IPv6Address") if (wi.get(k) or "") != (gi.get(k) or "")]
if missing or bad:
    sys.exit(f"aliases missing {sorted(missing)}; static IP mismatch {bad}")
PY
}

detach() {  # detach <container>: capture first, then disconnect; abort on any failure
  local c=$1
  capture_endpoint "$c"
  docker network disconnect "$AX_NET" "$c" || die "docker network disconnect $AX_NET $c failed" || return 1
  DETACHED+=("$c")
  ! attached_to "$c" "$AX_NET" || die "$c still attached to $AX_NET after disconnect" || return 1
}

# Re-attach only what we detached, with the captured aliases/IPs. Containers that fail stay in
# DETACHED so a second call (EXIT trap) retries them. Returns nonzero if anything failed.
restore() {
  local rc=0 c line args=() left=()
  for c in "${DETACHED[@]+"${DETACHED[@]}"}"; do
    if ! attached_to "$c" "$AX_NET"; then
      args=(); while IFS= read -r line; do [ -n "$line" ] && args+=("$line"); done < <(connect_args "$c")
      if ! docker network connect "${args[@]+"${args[@]}"}" "$AX_NET" "$c"; then
        echo "RESTORE FAILED: docker network connect $AX_NET $c" >&2; rc=1; left+=("$c"); continue
      fi
    fi
    if ! verify_endpoint "$c"; then
      echo "RESTORE NOT VERIFIED for $c on $AX_NET" >&2; rc=1; left+=("$c"); continue
    fi
    echo "restored $c on $AX_NET (aliases/static IPs verified)"
  done
  DETACHED=("${left[@]+"${left[@]}"}")
  return $rc
}

remember_writer_state() {
  WRITER_WAS_RUNNING=$(docker inspect "$1" -f '{{.State.Running}}')
}

restore_writer_state() {  # put the writer back exactly as we found it
  local w=$1 now
  [ -n "$WRITER_WAS_RUNNING" ] || return 0
  now=$(docker inspect "$w" -f '{{.State.Running}}')
  if [ "$WRITER_WAS_RUNNING" = true ] && [ "$now" != true ]; then docker start "$w" >/dev/null || return 1; fi
  if [ "$WRITER_WAS_RUNNING" = false ] && [ "$now" = true ]; then docker stop "$w" >/dev/null || return 1; fi
  [ "$(docker inspect "$w" -f '{{.State.Running}}')" = "$WRITER_WAS_RUNNING" ]
}

# Host memory gate: MemAvailable (Linux) or free+inactive+speculative pages (macOS).
available_mb() {
  if [ -r /proc/meminfo ]; then
    awk '/^MemAvailable:/ {print int($2/1024)}' /proc/meminfo
  elif command -v vm_stat >/dev/null; then
    vm_stat | awk -v ps="$(pagesize 2>/dev/null || echo 16384)" \
      '/Pages (free|inactive|speculative)/ {gsub("\\.","",$NF); s+=$NF} END {print int(s*ps/1048576)}'
  else
    echo -1
  fi
}
