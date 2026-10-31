#!/usr/bin/env bash
# Partition injector: target only a disposable network explicitly named by caller.
# Always restores connectivity, including signals and command failures.
set -Eeuo pipefail
if [[ $# -ne 3 ]]; then echo "usage: $0 <disposable-network> <api-container> <target-shard-container>" >&2; exit 64; fi
network=$1 api=$2 shard=$3
case "$network" in *round1*|*test*|*disposable*) ;; *) echo "refusing non-test network name: $network" >&2; exit 65;; esac
for c in "$api" "$shard"; do docker inspect "$c" >/dev/null; done
mapfile -t attached < <(docker network inspect "$network" --format '{{range .Containers}}{{.Name}}{{"\n"}}{{end}}')
for c in "$api" "$shard"; do
  if ! printf '%s\n' "${attached[@]}" | grep -Fxq "$c"; then echo "$c is not attached to $network" >&2; exit 66; fi
done
restore() {
  docker network connect "$network" "$api" >/dev/null 2>&1 || true
  docker network connect "$network" "$shard" >/dev/null 2>&1 || true
}
trap restore EXIT INT TERM HUP
# Remove only API's attachment to the target test network, not the shard or other nets.
docker network disconnect "$network" "$api"
echo "PARTITION ACTIVE: $api detached from disposable network $network; $shard remains attached"
echo "Run bounded API probes now; this script restores both attachments on exit. Ctrl-C also restores."
read -r -t 30 -p 'Partition window 30s; press Enter to restore early: ' _ || true
restore
trap - EXIT INT TERM HUP
echo "CONNECTIVITY RESTORED: $api and $shard attached to $network"
