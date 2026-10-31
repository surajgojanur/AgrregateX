# Issue31 test/demo readiness

1. Existing dashboard, Engine and Monitoring UI are outside this benchmark change. Do not use
   localhost8093 or round1-db as benchmark targets. Do not restart/migrate them.
2. Contract v2 is published in opus-sharding.md §5: A={1,3,4}, B={2,5..10}, host API8091,
   signed ax_session cookies, net_a contains API/writer/A only; net_b independently reaches B.
3. Screen correctness evidence must name hardware, real dataset size, runtime/digest, Git SHA,
   command and per-shard exact three-table oracle output. Simulated tests prove harness logic only.
4. Screen failure/recovery remains BLOCKED. After explicit authorization and disposable resource
   gate, use the gated reference wrapper described in README.md; A503, B reads/committed writes,
   explicit partial totals, recovery and both exact oracles must pass. Never improvise network commands.

Fedora Issue31 preflight: 7.5GiB RAM, 1.4GiB available, 5.1GiB swap used. No new containers, seeds,
network faults, SQL mutations or requests to existing API8093 were executed for this task.
10k/100k functional integration BLOCKED until a safe disposable host is available. 1M and 10M
are plan-only without separate explicit approval. G3 Mac evidence requires matching provenance,
workload and scale before acceptance; it cannot be silently substituted for another run.
