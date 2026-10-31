# B5 monitoring

Open `/app#/monitoring` after signing in as the demo operator. The endpoint `/api/monitoring` requires a valid signed operator session, unless explicit localhost operator demo mode is enabled. Tenant and anonymous requests cannot trigger database collection.

API metrics use ASGI middleware around existing routes: complete server response duration, successful p50/p95 only, errors and server-observed timeouts counted separately. Samples have no tenant, URL, SQL or user labels. At most 4096 samples over five minutes, process-local and reset on restart. Client-side timeouts and disconnected clients are not reliably observable. These samples are not official G-1 benchmark evidence.

The page polls after completion every 15 seconds, with no overlapping requests. A process-wide single-flight 15-second cache reuses engine.snapshot and FRESHNESS_SQL per shard, with existing database timeouts. There is no background polling or raw order scan. CDC rows are PostgreSQL statistics estimates. Refresh age is successful verification age including NO_DATA, not measured commit-to-visible lag. Health is degraded when the scheduler stops, refreshes fail, stream tables are inactive, verification is unknown/30s old, or engine health reports a problem. A failed shard collection shows unavailable without reusing stale values. A shard not configured is not invented.

Run unit/mock checks: `PYTHONPATH=hackathon/app python -m unittest discover -s hackathon/app/tests -p test_monitoring.py -v` (FastAPI/httpx/psycopg dependencies required).

Fedora preflight: 7.5 GiB total RAM, about 1.0 GiB available, 5.8 GiB swap used. Live database integration and runtime browser QA BLOCKED; existing containers untouched. No 10M performance claims. Unit and frontend check results are recorded in the PR.
