# P3 sharding benchmark scaffolding

**Real two-shard integration: BLOCKED** until Opus publishes the tenant-to-shard mapping, shard API behavior, and disposable network/containers. No simulated test below proves database sharding behavior.

Run deterministic contracts with `python3 -m unittest discover -s hackathon/benchmark/sharding -v`. These cover exact tenant mapping, duplicate/misplaced tenant rows, per-shard aggregate oracle (count/units/cents, nullable group keys, day boundary), fail-closed 503 mapping, and unaffected-shard continuation.

`partition.sh` is intentionally not run here. It refuses networks without a test/disposable marker, verifies both containers are attached, detaches only API from that network, and restores both attachments from EXIT/signal traps. It has a 30-second bounded window. Validate Docker provider's `network disconnect/connect` semantics in a dedicated disposable stack before use. Never target existing round1 or production containers.

`metrics.py URL` measures HTTP health/tenant endpoint request wall time and failures. Run separately per tenant mapped to each shard; record API commit-to-visible fields as freshness only if the API contract exposes and actually measures them. Do not infer throughput from HTTP latency; use a separately approved workload generator. Recovery time requires recording injection, restoration, and first successful target-shard request timestamps. All live metrics currently NOT TESTED.

Required later integration matrix: healthy A and B, partition A only, A endpoint returns bounded HTTP 503, B read/write still works, no cross-shard fallback, restore A in cleanup, first successful A read/write, per-shard EXCEPT ALL oracle for all 3 stream tables, and source/API RLS checks. Test process failure separately; one host remains one physical failure domain.
