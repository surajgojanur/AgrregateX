#!/usr/bin/env bash
# Gate and reuse the current reference injector. Never touches a network by default.
set -Eeuo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
[[ ${AX_FAULT_APPROVED:-0} = 1 && ${AX_DISPOSABLE:-0} = 1 ]] || { echo 'BLOCKED: explicit live fault approval and disposable stack required' >&2; exit 2; }
[[ ${AX_PROJECT:-aggregatex-sharded} = aggregatex-sharded ]] || { echo 'BLOCKED: reference contract requires aggregatex-sharded' >&2; exit 2; }
[[ ${AX_BASE:-http://127.0.0.1:8091} = http://127.0.0.1:8091 ]] || { echo 'BLOCKED: require contract loopback endpoint' >&2; exit 2; }
LOCK="${XDG_RUNTIME_DIR:-/tmp}/aggregatex-sharded-benchmark-fault.lockdir"
mkdir "$LOCK" || { echo 'BLOCKED: another fault test or retained lock requires review' >&2; exit 2; }
trap 'rmdir "$LOCK"' EXIT
python3 "$HERE/preflight.py"
# Reference owns exact project/network checks, host cookies, A-only API+writer detach,
# attachment restoration, writer state, B committed write and bounded recovery assertions.
bash "$ROOT/sharding/partition_demo.sh" "${1:-5}"
# Its sum-only oracle check is insufficient for coverage. Require exact three-table output
# on BOTH shards as an additional fail-closed gate. No parallel competing writers permitted.
python3 "$HERE/verify_oracles.py"
