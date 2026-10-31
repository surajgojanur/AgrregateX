# OPUS handoff: P3 two physical tenant shards, tenant router, partition-aware dashboard (issue #19)

**Status:** implemented and demonstrated on the Opus Mac (M1, Docker VM 3.8 GiB, host under memory pressure). This is a
bounded demo with **10,000 orders TOTAL** of REPRESENTATIVE data, no 10M, and n=1 indicative runs.
**Branch:** `feat/opus-p3-sharding`, stacked on PR #18 (`feat/hackathon-dashboard-api`).
**Not claimed:** automated failover, replication, quorum, AP behaviour, 10M acceptance, or G-1..G-5 compliance.

## 1. What was built
| Piece | Where | Notes |
|---|---|---|
| Two independent PG 18.6 + pg_trickle 0.108.3 instances | `compose.sharded.yaml` services `shard_a`, `shard_b` | Separate volumes and networks (`net_a`, `net_b`). Each has its own scheduler, the three stream tables, roles, RLS and oracle. `mem_limit 512m`, `shared_buffers=64MB`. |
| Versioned tenant→shard directory | `sharding/directory.v1.json` | v1: **A = {1,3,4}, B = {2,5,6,7,8,9,10}**. Explicit and stable; never reassign tenants by modulo once rows exist. |
| Deterministic sharded seed | `sharding/seed_shard.sql` | Same global dataset on both shards, each filtered to its own tenants. Order id `n` lives on exactly one shard. |
| Router at the connection factory | `app/axapi/db.py` | Per-shard pools for `ax_api`, `ax_writer` and `ax_monitor`. `tenant_tx(role, tenant)` routes by directory. **Auth runs before routing** (`main.tenant_path`). |
| Fail-closed outage handling | `db.ShardUnavailable` → HTTP **503** + `Retry-After: 5` | Bounded by `connect_timeout=2s`, pool wait `3s`, `tcp_user_timeout=3s`, server `statement_timeout=5s`. **No cross-shard fallback.** |
| Operator `/api/shards` | `engine.shards_overview()` | Per shard: probe, tenants, stream-table status and age, pending CDC rows, order counts, directory violations. Global `total_orders` is **null unless every shard answered**; otherwise `partial_total_orders` with `complete=false`. |
| Existing contract kept | `/api/tenants/{id}/…` | Responses add `shard`. `/api/tenants` is served from the directory, so it still answers while a shard is down. `/api/engine?shard=a\|b` |
| Live writer | `app/axapi/writer.py` | 2 changes/s by default. Each write goes to the owning shard; while that shard is down it is skipped and counted, never redirected. |
| Dashboard | `frontend/src/pages/{Dashboard,Shards,Engine}.jsx` | Shows the tenant's shard and directory version. On 503 the old numbers are **dropped** (no stale data shown) and a "Shard X unavailable" banner appears. New **Shards** page; Engine has a shard picker. |
| Aggregate-only counts for the operator | `sql/25_app_roles.sql` `ax.tenant_order_counts()` | SECURITY DEFINER per-tenant totals; `ax_monitor` still never reads order rows. |

### Failure semantics (documented contract)
- **Owning shard unreachable:** that tenant's reads and writes return **503** within about 3 s. The body names the shard; nothing is served from another shard.
- **Other shards:** unaffected.
- **A 503 on a write means "not confirmed".** A write that is *confirmed* committed is never reported as failed. If the shard drops after the commit, the response is 200 with `committed: true` and `visibility_error` set.
- **Global views:** never present a partial total as complete.
- **Recovery:** automatic. Pools reconnect, and the shard's own scheduler has kept refreshing locally throughout.

## 2. Measurement-rule fix (affects PR #18's live-write)
The PR #18 live-write rule ("visible when the stream table's frontier LSN ≥ the commit LSN") was **wrong when the source is idle**.
pg_trickle's frontier records the LSN of the last *consumed change*. That is below the commit record's LSN and doesn't advance on
NO_DATA refreshes, so with the writer paused it never "became visible".

The replacement rule is data-based. Poll until, in **one snapshot**, every stream-table row the change touched (old and new status
groups) equals the same aggregate computed from raw `ax.orders`. That proves visibility *and* correctness.

The earlier single-DB lag numbers (about 2 s) were measured with the writer running, so the frontier did move past. They remain
valid upper bounds.

## 3. Acceptance evidence (all in `sharding/results/`)
| Acceptance item (#19) | Result | Evidence |
|---|---|---|
| A and B hold disjoint tenant and order rows; global counts match the seed | **PASS.** A = {1,3,4} with 5,013 seed orders; B = {2,5..10} with 4,987. The union is exactly ids 1..10,000 with 0 duplicates, and joins are tenant-local (0 orphans). | `baseline-shard-check.json` |
| Baseline per-shard oracle | **PASS:** 0/0 on all 3 stream tables per shard, writer paused | same |
| Correct API results for a tenant on A and on B | **PASS:** API vs SQL on the *owning* shard, **200/200** (tenants 1 and 3 on A, 2 and 5 on B; summary, Top-10, category, day/hour trends; 10 windows each) | `baseline-api-oracle.txt` |
| One real mutation per shard appears in its local stream tables | **PASS.** Insert on A lands on A only and is visible in 1.53 s; on B, 1.48 s. Cancels: 1.46 s and 1.48 s. | `baseline-shard-check.json` |
| Cross-tenant 403 (auth before routing) | **PASS.** Tenant 2 (B) reading tenant 1 or 3 (A) → 403; cancelling tenant 1's order → 403; `/api/shards` → 403; no session → 401. | same |
| Partition of A: A fails explicitly, B succeeds, no leakage or false writes | **PASS.** See below. | `partition-20261031T122030Z.txt` |
| On recovery, A's oracle passes | **PASS:** 0/0; API count = SQL count (65) for the last 10 minutes, including 25 inserts made locally during the partition | same |

### Partition run (2026-10-31T12:20Z; 47 s partition; the API and writer detached from `net_a` only)
| Probe | Result |
|---|---|
| tenant 1 / 3 (shard A) summary, top-products | **503** in 3.01–3.27 s, body `{"shard":"a","retryable":true,…}` |
| tenant 1 (A) live-write insert | **503** (3.0 s). Shard A rows before and after = only the 25 local inserts, so **no phantom write** |
| tenant 2 / 5 (shard B) summary, trends | **200** in 13–26 ms |
| tenant 2 (B) live-write | **200**, visible in about 1.5 s |
| `/api/health` | `degraded`, shard a `available:false` (PoolTimeout) |
| `/api/shards` | `complete=false`, `missing=['a']`, `total_orders=null`, `partial_total_orders=5051` |
| writer during the partition | `ok:b 11`, `skipped:a 9`, 0 redirected |
| recovery after reattaching | tenant 1 → 200 within **3 s** |

### Measurements (n=1, laptop, indicative; **not** G-1..G-5 evidence)
| Metric | Result | File |
|---|---|---|
| HTTP latency, 100 requests per endpoint, range from 2026-08-01 | Shard A tenant 1: p50 4.3–5.5 ms, p95 6.1–9.8 ms, max 47 ms. Shard B tenant 2: p50 3.5–4.5 ms, p95 6.0–8.7 ms. | `measure-latency-lag.json` |
| Commit → visible (10 inserts per shard, writer at 2/s) | A: p50 1.24 s, max 1.85 s. B: p50 1.27 s, max 1.54 s. 10/10 visible on each. | same |
| OLTP throughput on shard A (pgbench 4 clients × 20 s, two repetitions) | No dashboard load: **1,150 / 1,277 tps** (3.5 / 3.1 ms). With dashboard load (about 140 req/s on A's tenants): **541 / 615 tps** (7.4 / 6.5 ms). **Mean −52% throughput: a FAIL** against G-3's 10% / 25% targets. Confounded by one machine sharing all CPUs (client, API, load generator, both shards) and by refresh cost (P1 finding F3). | `oltp-delta-shard-a.txt` |
| Correctness after load | Both shards 0 mismatches within 6 s of pausing writes | same |
| Resources (after load) | shard_a 155 MiB / 512, shard_b 122 MiB / 512, api 51 MiB / 256, writer 29 MiB / 128 | same |

## 4. Runbook
```bash
cd hackathon
docker compose -f compose.sharded.yaml up -d --build             # http://127.0.0.1:8091 (no login by default)
AX_AUTH_DISABLED=0 docker compose -f compose.sharded.yaml up -d --no-deps api   # login on, for the 403 checks
docker compose -f compose.sharded.yaml stop writer && sleep 6     # quiesce before the oracles
python3 -I sharding/tests/shard_check.py                          # acceptance checks (JSON)
AX_BASE=http://127.0.0.1:8091 AX_TENANT_DSNS='{"1":"host=127.0.0.1 port=25571 dbname=aggregatex user=postgres password=local-demo-superuser","2":"host=127.0.0.1 port=25572 dbname=aggregatex user=postgres password=local-demo-superuser"}' python3 -I app/tests/api_oracle.py 10
sharding/partition_demo.sh 20                                     # partition and recovery; touches net_a only
python3 -I sharding/measure.py 100 10                             # latency and lag
docker compose -f compose.sharded.yaml stop                       # keeps volumes
```
Ports: API 8091; shard A 25571; shard B 25572 (all `127.0.0.1`). Networks: `aggregatex-sharded_{edge,net_a,net_b}`.
The single-DB stack (`compose.yaml`, port 8090) is untouched and can run alongside.

## 5. Sharded API / network contract (v2) for the Codex harness (PR #21)
| Item | Contract |
|---|---|
| Host endpoints | API `http://127.0.0.1:8091` · shard A `127.0.0.1:25571` · shard B `127.0.0.1:25572` (superuser `postgres`, password `$AX_DB_SUPERUSER_PASSWORD`, demo default `local-demo-superuser`) |
| Networks | `aggregatex-sharded_net_a` = **API + writer + shard_a only** (the A-only fault target); `aggregatex-sharded_net_b` = API + writer + shard_b; `aggregatex-sharded_edge` = API + writer only, with `gw_priority 10` so the published port never depends on a shard network. Shard B is never on `net_a`. |
| Aliases | Shards are reached by compose service names `shard_a` / `shard_b`. Those aliases belong to the **shard** containers, so detaching or reattaching the API or writer does not need aliases restored. Neither the API nor the writer has a static IP. |
| Auth | **Not Bearer.** HttpOnly cookie `ax_session` from `POST /api/auth/login {"email","password"}` (demo users `tenant<N>@demo.local`, `admin@demo.local`, password `$AX_DEMO_PASSWORD`). With `AX_AUTH_DISABLED=1` (compose default) every request is the operator. Never print the cookie. |
| HTTP client | Probe from the **host** against `127.0.0.1:8091`. The API image (`python:3.14-slim`) has **no curl**; `docker exec … python -c 'urllib…'` works if an in-container probe is required. |
| Read probe | `GET /api/tenants/{id}/summary` → 200, or **503** `{"shard":"a","retryable":true}` with `Retry-After: 5` within about 3 s when the owner is unreachable |
| Write probe | `POST /api/tenants/{id}/live-write {"action":"insert"}` → 200 `{"committed":true,"shard":…,"order_id":…,"lag_ms":…}`, or 503 (not confirmed) |
| Global view | `GET /api/shards` (operator) → `complete`, `missing_shards`, `total_orders` (null unless complete), `partial_total_orders` |
| Directory | `sharding/directory.v1.json`: A = {1,3,4}, B = {2,5,6,7,8,9,10} |
| Oracle | `SELECT * FROM ax.oracle_mismatches()` on each shard (missing and extra, all three grains); quiesce the writer first |
| Reference fault script | `sharding/partition_demo.sh`: preflights Docker and containers, aborts if shard B is on `net_a` or the API lacks `net_b`, detaches only the API and writer, re-attaches only what it detached, and exits nonzero unless the restore is verified (attachment + tenant-1 200 + `/api/shards complete=true`). The hardened revision is **NOT RUN** yet: the Docker daemon stopped on the Opus Mac after the first run. The first run (results above) used the earlier, less defensive restore. |
| Image | `AX_PG_TRICKLE_IMAGE`; the default digest `sha256:94344bb9…` is an OCI index with **only linux/arm64**, so amd64 hosts must supply their own image |

## 6. Limits and next steps (proposals, not done)
- **No replica or leader election:** while shard A is down its tenants are unavailable (CP per shard). Follow-up proposal: a streaming replica per shard plus manual or automatic promotion, with directory v2 carrying the endpoints.
- **Directory changes:** require a restart. Moving a tenant needs a copy, verify, flip, then delete procedure, plus directory v2.
- **G-3 under load fails:** an isolated benchmark host (Codex harness) and P1 are needed before any claim.
- **Fault injection and benchmarks under `hackathon/benchmark/**`:** Codex. This doc publishes the ports and network names above.
