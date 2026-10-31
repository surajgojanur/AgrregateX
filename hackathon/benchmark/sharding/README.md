# P3 sharding benchmark scaffolding

**Real two-shard integration: BLOCKED** until Opus publishes tenant routing, API, and a disposable network/container contract. Simulated tests are not evidence of database sharding behavior.

Run unit contracts with `python3 -m unittest discover -s hackathon/benchmark/sharding -v`. The independent oracle mirrors all three stream definitions: tenant/day/product/status; tenant/day/category/status; tenant/hour/category/status. Results compare both missing and extra key/value pairs. Directory completeness is tested separately, so mapped zero-order tenants are valid.

`partition.sh` is deliberately not run here. It targets only the shard-A-specific test network, requires API A+B and shard A membership, rejects shard B on that network, and probes B before/during/after partition. It snapshots aliases and IP addresses, restores only shard A's removed network attachment, and verifies attachment metadata plus API-to-A/B health before reporting cleanup success. This cannot protect against SIGKILL or host power loss. No partition test is safe until Opus provides a disposable topology.

`metrics.py URL` reports successful 2xx latency p50/p95 using nearest-rank percentiles separately from HTTP errors and timeouts. Measures observed requests only. Freshness requires a real committed mutation and actual visible aggregate; do not substitute timestamps. Throughput requires a bounded workload and should be reported separately.
