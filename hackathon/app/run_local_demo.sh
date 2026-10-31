#!/usr/bin/env bash
# Explicit local operator demo; no seeds, database changes, or writer started.
set -euo pipefail
cd "$(dirname "$0")"
export AX_AUTH_DISABLED=1 AX_ENABLE_DEMO_WRITES=0
export AX_STATIC_DIR="$(cd ../frontend/dist && pwd)"
exec python -m uvicorn axapi.main:app --host 127.0.0.1 --port "${AX_LOCAL_DEMO_PORT:-8093}"
