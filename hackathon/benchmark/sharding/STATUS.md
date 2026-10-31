# P3 evidence status

| Requirement | Status | Evidence |
|---|---|---|
| Tenant mapping exactly one known shard | Simulated PASS | `test_mapping_requires_exact_tenants_and_known_shard` |
| Per-shard aggregate oracle, nullable dimensions, day boundary | Simulated PASS | `test_per_shard_oracle_nullable_keys_and_time_edges` |
| Detect tenant duplication/misplacement | Simulated PASS | `test_duplicate_or_misplaced_tenant_fails` |
| Unavailable shard gives 503; other shard continues | Simulated contract PASS | `test_unavailable_returns_503_and_other_shard_works` |
| Unknown tenant fails closed | Simulated PASS | `test_unmapped_tenant_fails_closed` |
| Actual API and database on two shards | BLOCKED | Waiting for Opus implementation and endpoint/mapping contract |
| Disposable network partition and automatic restore | NOT RUN | Script exists; no verified disposable shard network is available |
| Live latency, freshness, recovery, throughput | NOT TESTED | Collector interface only; must run after integration |
| 1M / 10M | NOT RUN | No large workload permitted in this scaffold; 10M requires approval |

Run simulated suite: `python3 -m unittest discover -s hackathon/benchmark/sharding -v`.
`partition.sh` is not executed by tests and requires explicit disposable containers/network.
