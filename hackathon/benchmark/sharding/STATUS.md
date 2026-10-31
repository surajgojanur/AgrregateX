# P3 evidence status

| Requirement | Status | Evidence |
|---|---|---|
| Tenant mapping complete, unique and known shard | Simulated PASS | test_model.py |
| Correctly mapped zero-order tenants permitted | Simulated PASS | test_model.py |
| Three independent stream grains and nullable keys | Simulated PASS | model.py oracle_streams + test_model.py |
| Both-direction aggregate comparison | Simulated PASS | multiset_mismatches unit case |
| HTTP 503 separated from successful latency/timeouts | Simulated PASS | test_metrics.py |
| Fault network isolated to shard A | Safety validation implemented; not executed | partition.sh + test_network_safety.py |
| Network restoration verifies aliases/IP/connectivity | Implemented; not executed | partition.sh |
| Actual API and database on two shards | BLOCKED | Waiting for Opus implementation/contract |
| Live latency, freshness, recovery, throughput | NOT TESTED | No live sharding stack available |
| 1M / 10M | NOT RUN | not authorized/necessary here |

Run tests: `python3 -m unittest discover -s hackathon/benchmark/sharding -v`.
The network injector is never invoked by tests and is not run against existing services.
