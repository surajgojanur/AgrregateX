# G3 database-safety A/B (issue #28)

PRD G3: normal OLTP queries should be **< 25% slower (Good) / < 10% slower (Great)** while dashboards are in use.
This harness measures it with matched, randomised arms on **one** disposable shard server.

| Arm | Database | Stream tables + CDC | Background writer | Dashboard HTTP load |
|---|---|---|---|---|
| **A** | `aggregatex` | yes | yes (2 changes/s) | none |
| **B** | `aggregatex` | yes | yes | **fixed offered rate** (`--http-rate`) through the real API: summary / trends / top-products / breakdown for tenants 1, 3, 4 |
| **C** | `ax_nost` (same seed, schema and bucket trigger) | **no** | (it writes only `aggregatex`) | none |

- **B vs A** = the dashboard's effect on OLTP (**the G3 question**).
- **A vs C** = the cost of incremental maintenance itself (CDC triggers + refresh), kept separate rather than conflated with G3.

**Method**
- **Ordering:** each pair runs A, B and C in a random order (seed recorded in `meta.json`).
- **Per arm:** one `pgbench` run of `--clients` clients for `--seconds`. `--oltp-rate N` fixes the offered OLTP rate (`pgbench -R`); with a fixed rate, the G3 signal is **latency** (p50/p95/p99, measured from the scheduled start, so queueing counts) rather than throughput. Per-transaction logs give p50/p95/p99; the first `--warmup` seconds are discarded.
- **Reset:** between arms, pgbench's inserted rows (`order_id >= 300,000,000`) are deleted and vacuumed. For `aggregatex` the harness then waits until the CDC backlog has drained and refreshes are current.
- **Sampled every 2 s:** lock waits, CDC backlog and refresh age. Per arm also: the refresh-history actions, fallbacks and failures in the window, container CPU/RAM at mid-arm, and **commit→visible probes** (insert + cancel via `/live-write`, tenant 3) in arms A and B.
- **HTTP:** offered vs achieved rate, status counts and errors, latency p50/p95/p99 (successful requests only).

**Run** (disposable project only; it deletes pgbench rows and creates `ax_nost`):
```bash
cd hackathon
AX_API_PORT=18191 AX_SHARD_A_PORT=25671 AX_SHARD_B_PORT=25672 \
  docker compose -p ax-g3-10k -f compose.sharded.yaml up -d --build --wait
cd integration/g3
python3 -I g3_ab.py --project ax-g3-10k --port 25671 --api http://127.0.0.1:18191 \
  --pairs 5 --seconds 35 --warmup 5 --http-rate 20 --seed 2801 --out results/10k-r20
```
Outputs: `results/<run>/meta.json` (arguments, workload, versions, row counts), `arms.jsonl` (every arm, raw), and
`summary.json` (per-pair deltas plus median/min/max).

**Limits (always stated with results).**
- One Apple M1 laptop runs everything: client, API, load generator and both shards share its CPUs.
- Representative data (10k / 100k orders), not the PRD's 1M/10M.
- The workload is representative store traffic, not an organiser-supplied OLTP suite.
