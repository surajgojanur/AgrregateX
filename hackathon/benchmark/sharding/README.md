# P3 v2 benchmark harness (#31 / draft #21)

The contract exists: `hackathon/docs/handoffs/opus-sharding.md` §5, merged main.
Real two-shard integration remains **BLOCKED by resource/approval gates**, not an unpublished API.

Run lightweight checks:

```
python3 -m unittest discover -s hackathon/benchmark -v
python3 -m unittest discover -s hackathon/benchmark/sharding -v
bash hackathon/sharding/tests/test_lib_partition.sh
bash hackathon/sharding/tests/test_partition_demo.sh
```

Host metrics: set AX_DEMO_PASSWORD privately in the environment, then
`python3 hackathon/benchmark/sharding/metrics.py --base http://127.0.0.1:8091 --path /api/tenants/2/summary --count 30`.
Uses POST /api/auth/login and in-memory HttpOnly ax_session cookie handling; no Bearer tokens,
no curl inside API, no credentials/cookies in evidence. Successful-only p50/p95; errors/timeouts separate.
These metrics are observations, not acceptance proof.

`partition.sh` is NOT RUN. It delegates to the existing reference `hackathon/sharding/partition_demo.sh`.
Default invocation refuses before Docker. Requires AX_FAULT_APPROVED=1 (only after explicit human
approval), AX_DISPOSABLE=1, the exact aggregatex-sharded project/localhost8091 contract,
2GiB available RAM, <=1GiB swap used, 5GiB free disk, exactly the two expected project database
volumes carrying io.aggregatex.disposable=true and attached to their expected shard containers.
These labels must be assigned when provisioning NEW disposable volumes; never relabel existing ones.
Writer must already be quiesced; no competing writers. The reference then validates exact Compose
ownership/network membership and detaches API+writer from net_a only. It asserts A503 with shard a,
B successful reads and committed/visible writes on B only, partial global totals, bounded recovery,
network alias/address restoration and original writer state. The wrapper additionally rejects missing,
duplicate, nonzero or boolean-valued oracle counts on either shard. Signal cleanup does not survive
SIGKILL/power loss. No source/volume cleanup command is included here.

The reference has fixed ports and mutates disposable source rows; do not point it at round1, 8093,
or other existing data. Mock tests and logged reference PASS do not constitute official qualification.
