# Issue #31 safe execution runbook

Run from repository root. Never use existing demo volumes, stop its services,
apply migration 003, run a partition, or rebuild its stream tables.

## Preflight and offline tests

```bash
git fetch origin
git worktree list
git status --short
free -h
df -h /home
vmstat 1 5
docker ps --format '{{.Names}} {{.Ports}}'
ss -ltn
python3 -m unittest discover -s hackathon/benchmark -p 'test_*.py' -v
python3 -m unittest discover -s hackathon/benchmark/sharding -p 'test_*.py' -v
just fmt
just lint
```

Stop before stack creation unless available RAM >=4 GiB, swap used <=1 GiB,
no sustained swap-in/out, free persistent disk >=15 GiB, and teammate ownership
and ports/volume absence are verified. Require the operator's exact target approval.
These are conservative gates, not measured capacity guarantees. Current Fedora fails.

## Preserved demo, small read-only checks only

SQL-verify min/lower-median/max tenant first (this run: 6/7/1). Each invocation
uses a new directory and defaults to a tiny request budget. No sustained load.

```bash
python3 hackathon/benchmark/http_baseline.py --base http://127.0.0.1:8094 \
  --tenants 6 7 1 --cases 4 --samples 1 --warmup 1 \
  --allow-auth-bypass-smoke --out /tmp/ax31-new-http
python3 hackathon/benchmark/read_only_compare.py --container round1-db \
  --http /tmp/ax31-new-http/http.json --out /tmp/ax31-new-sql
```

Comparator is deliberately limited to <=10k rows; it reads raw sources and
recomputes selected numeric fields independently, never imports API aggregation
helpers. It derives SQL oracle SELECTs from `hackathon/sql/30_oracle.sql` without
installing its functions. Exit 1 means mismatch; preserve it. No automatic repair.
HTTP/SQL observations are separate; only the three-table oracle is one snapshot.

## Proposed disposable 10k then 100k (NOT APPROVED / NOT EXECUTED)

Exact requested target: same Fedora host only after resource gate; projects
`ax-issue31-10k` / `ax-issue31-100k`; containers `<project>-db-1` and
`<project>-api-1`; loopback ports 25631/18131 and 25632/18132;
fresh volumes `<project>_scaledata`. Do not run concurrent stages. Reserve
2 GiB DB + 512 MiB API, two CPUs total, >=2 GiB demo/system headroom,
15 GiB free disk, 20-minute stage ceiling. Abort on swapping, demo errors,
remaining RAM <2 GiB, timeout or correctness failure. Stop only owned disposable
containers if authorized; retain volumes/evidence. No deletion commands here.

After explicit approval and ownership checks, create a local override:

```yaml
# /tmp/ax31-budget.yaml (prepare manually, inspect compose config before launch)
services:
  db:
    cpus: 1.5
  api:
    mem_limit: 512m
    cpus: 0.5
    environment:
      AX_AUTH_DISABLED: "0"
      AX_ENABLE_DEMO_WRITES: "0"
```

Only after approval, copyable 10k commands (100k substitutes project, counts,
ports and new volume; inspect exact names before executing):

```bash
cd hackathon
export AX_SEED_ORDERS=10000 AX_SEED_TENANTS=10 AX_SEED=42
export AX_SCALE_DB_PORT=25631 AX_SCALE_API_PORT=18131 AX_SCALE_DB_MEM=2g
export AX_AUTH_DISABLED=0
docker compose -p ax-issue31-10k -f compose.scale.yaml -f /tmp/ax31-budget.yaml config
# APPROVAL GATE: do not execute following command on current pressured host
docker compose -p ax-issue31-10k -f compose.scale.yaml -f /tmp/ax31-budget.yaml up -d db api
docker exec -i ax-issue31-10k-db-1 psql -X -U postgres -d aggregatex \
  -v ON_ERROR_STOP=1 < integration/scale/verify_dataset.sql
```

No writer service. The existing generator bootstraps before stream creation.
Use secure local password provisioning; never capture env/config containing passwords.
Acquire an actual `ax_session` through `/api/auth/login` with CookieJar (existing
`hackathon/benchmark/sharding/http_probe.py` login helper); retain only in memory
or temporary mode-0600 local file. Never place cookie/password in evidence.
Sampler accepts `AX_SESSION_COOKIE` from the environment and verifies `/api/auth/me`.
Check anonymous 401 separately; operator identity alone cannot prove auth enabled.

## Approval-gated 1M

Require both smaller stages' complete counts, zero exact oracle differences,
no errors, measured resource peaks and separate explicit authorization. Proposed
project `ax-issue31-1m`, ports 25633/18133, containers `ax-issue31-1m-{db,api}-1`,
volume `ax-issue31-1m_scaledata`; same 2 GiB DB/512 MiB API/two-CPU cap,
>=4 GiB available RAM before startup, 15 GiB disk, 30-minute setup ceiling.
Historical 648 MB database is a lower bound, not peak memory/WAL evidence.
Use the same existing Compose/generator with 1000000/10 and seed42; never point
it at `round1-db`. No one-million load is authorized by this document.

For an approved target prepare provenance JSON containing string fields
`approval_reference`, `git_sha` (40 hex), `image_digest`, `hardware`,
`config_sha256` and `dataset_sha256` (64 hex), `dataset_seed`, `database_identity`,
`project`, `preflight_utc`, plus `base`, integer `orders`, `populated_tenants:10`,
`dataset_kind:"synthetic"`, `disposable:true`, `preflight_pass:true`.
These operator assertions do not replace live SQL/preflight verification.

```bash
python3 hackathon/benchmark/http_baseline.py --base http://127.0.0.1:18133 \
  --tenants MIN_ID LOWER_MEDIAN_ID MAX_ID --cases 48 --samples 200 --warmup 48 \
  --approved-disposable-metadata /tmp/ax31-approved-provenance.json \
  --out /tmp/ax31-approved-1m-http
```

This runs 9,600 measured requests, serial <=10 requests/s, closed-loop pacing;
it is not an open-loop throughput stress test. All failures/timeouts are retained.
Nearest-rank successful-response p50/p95/p99, mean/min/max, elapsed/completed rate
are stored in JSON/Markdown; errors cannot count as fast responses. No cache-flush
operation is permitted. Per-scenario analysis is required; pooled tails are insufficient.
For scale source comparisons use the existing `api_oracle.py` against the approved
target with explicit DSN, writes disabled; its legacy defaults must never be used.
Extend grouped oracle capture to all 48 cases before declaring scale correctness.
Record all count/skew/status/product/date/seed/duration/version/digest/mode evidence
from `verify_dataset.sql` inside an explicit READ ONLY consistent snapshot.
Capture per-direction missing/extra with the existing oracle SELECTs.

G2 probes remain separately gated: dedicated unique keys, separate reader,
monotonic timestamp immediately after COMMIT, exact expected values, timeout
censoring retained; idle and bounded sustained writes separate. No mutations
against the preserved demo. Reuse owner-maintained G3 instrumentation, coordinate
before any experiment, and never infer visibility from refresh timestamps.

## 10M plan only and G5

No executable 10M command is provided. Separate approval required after 1M succeeds.
Proposed future resourced host: >=16 GiB RAM (estimate), >=8 GiB available before
startup, >=30 GiB free disk (conservative unmeasured allowance for heap/index/WAL),
no active swapping. Determine peak needs from smaller stages first. Match the host,
image/config/source SHA, serial client, warmup, seed and query definitions between
1M/10 and 10M/100. Rank tenants by actual counts with deterministic lower-median
selection and ID tiebreak. Use the same UTC anchor and window/endpoint parameters.
Compare each of 48 real p95 pairs, disclose every ratio/error; no imagined denominator
or averaging away failed cases. Extra daily/hourly, status/category, empty/exact
boundary and tie cases supplement the canonical matrix. G5 remains NOT TESTED.

## Reports

```bash
python3 hackathon/benchmark/evidence_report.py hackathon/benchmark/results/issue31/20261101-fedora
git diff --check
```

This conservative small-demo scorecard never grants official acceptance. Existing
`acceptance.py` validates complete official evidence separately, distinguishes
`automated_candidate_pass`, and always leaves `official_pass` false pending review.
