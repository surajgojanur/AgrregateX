# P3 benchmark contract proposal

This contribution is benchmark-only and does not implement routing or shards.

The test boundary expects `tenant_id -> shard_id`, a callable per shard, and source
rows available per shard for a direct aggregate oracle. Every configured tenant must
map to one known shard; each tenant's rows must occur on exactly that shard. Oracle
keys include tenant, day, nullable product/category, and status; values include count,
units, and integer cents. Production SQL oracle must compare `EXCEPT ALL` in both
directions independently on each database.

During a partition, requests for the affected tenant's unavailable shard must fail
with HTTP 503 within a bounded client timeout. Requests to another shard must continue.
No fail-open rerouting is allowed. Recovery timing starts when connectivity is restored
and ends at the first successful target-shard operation; freshness must be measured
from committed write to exact visible state. Process failure is a separate experiment.

Current contract status: simulated tests pass; real two-shard integration BLOCKED
pending Opus API/mapping implementation. `partition.sh` has safety checks and cleanup
traps but remains unrun until dedicated disposable network artifacts are provided.
