# Mac two-shard judge walkthrough (3–5 minutes): issue #42 P0-1

**Proof scope.** Two independent physical PostgreSQL 18.6 + pg_trickle 0.108.3 shards on **one Mac**, built from `main` @ `2cc3a75`.
- Each shard is its own container, data volume and network; the API reaches them over separate networks.
- One host is one failure domain. This proves tenant sharding, routing and fail-closed behaviour; it does **not** prove HA.
- **Do not confuse it with Fedora's one-shard view.**

## 0. Start (about 60 s, before the judges arrive)
```bash
cd hackathon
AX_API_PORT=8092 AX_SHARD_A_PORT=25591 AX_SHARD_B_PORT=25592 \
  docker compose -p ax-demo42 -f compose.sharded.yaml up -d --build --wait
open http://127.0.0.1:8092            # landing page
```
Logins (local demo password `demo1234`): `admin@demo.local` (operator), `tenant1@demo.local` (shard A), `tenant2@demo.local` (shard B).

## 1. Story (screens: `ui/*.png`)
| Time | Show | Say |
|---|---|---|
| 0:00 | Landing (`01-landing-*.png`), theme toggle, mobile width | "AggregateX: per-tenant dashboards served from incrementally maintained pg_trickle stream tables." |
| 0:30 | Log in as **tenant2** → dashboard (`04-tenant2-dashboard.png`): KPIs, sales-by-day, Top-10, breakdown, "Tenant 2 lives on shard B" | "All four mandatory query families. Each card shows its own server latency, here 77–90 ms." |
| 1:15 | As tenant2, try `#/engine` → refused; the operator nav is hidden | "Tenant isolation: API authorization plus row-level security. Other tenants are 403 *before* routing." |
| 1:45 | Log out, log in as **admin** → Shards page (`06-shards.png`) | "Two physical shards; directory v1: A = {1,3,4}, B = {2,5–10}; per-shard totals." |
| 2:15 | Switch tenant 5 → 1: data loads from the other shard | "Routing is by a stable directory, never by modulo." |
| 2:45 | Engine page (`07-engine.png`) and Monitoring (`08-monitoring.png`) | "Refresh history, modes and B-3 limits. B-5 is **partial**: monitoring shows the scheduler and freshness; the operator health facade (#38) is not deployed." |
| 3:30 | Terminal: the commands in §2 (pre-run output is in this folder) | "Correctness: every number equals raw SQL; the stream tables equal their sources on both shards." |
| 4:15 | Outage (recorded evidence only) | "If shard A is unreachable: tenants on A get **503** in about 3 s and totals are marked partial (`partial_total`); shard B keeps serving; recovery took under 3 s." |

**Do not click "Insert order" in the UI during the demo.** See §3: after a browser session, live writes on shard B currently time out. Show the measured commit→visible numbers from §2 instead.

## 2. Evidence commands (all run on this stack; output saved here)
| Command | Result | File |
|---|---|---|
| `AX_BASE=http://127.0.0.1:8092 AX_SHARD_A_PORT=25591 AX_SHARD_B_PORT=25592 python3 -I sharding/tests/shard_check.py` | **18/18 PASS**: tenants match the directory, no overlap, 10,000 seed = 5,013 A + 4,987 B, 0 duplicate ids, 0 orphans, both oracles 0/0 (writer paused), a live insert and cancel per shard visible in 0.8–1.5 s, cross-tenant 403s, 401 unauthenticated | `shard_check.json` |
| `SELECT * FROM ax.oracle_mismatches()` on both shards, writer paused | **0/0 on all 3 stream tables on both shards** | `oracle-quiesced.txt` |
| `api_oracle.py 25` with `AX_TENANT_DSNS` for tenants 1, 3, 4 (A) and 2, 7, 10 (B) | **744 checks, 0 mismatches** (summary, Top-N, category, hourly/daily trends) | `api_oracle.txt` |
| `ui_qa.py http://127.0.0.1:8092 ui full` (Playwright/Chromium) | **13/14 PASS, 0 JS errors**; FAIL: UI live write (§3) | `ui_qa.txt`, `ui/` |
| `AX_DRY_RUN=1 AX_PROJECT=ax-demo42 … sharding/partition_demo.sh 30` | **DRY RUN OK (no change made)**: preflight only, no network detached | `partition-dryrun.txt` |
| Recorded outage run (earlier, `aggregatex-sharded`) | A-tenants 503 in about 3 s; `complete=False missing=['a'] partial_total=5051`; recovered within 3 s | `../../../sharding/results/partition-20261031T122030Z.txt` |

## 3. Known limitations (state them if asked)
- **G2 live write after browser sessions (FAIL, contained).** API live writes for shard-B tenants time out at 30 s once the API process has served a UI session. During each such request, shard B's scheduler enqueues **no jobs at all** (not even NO_DATA), and refreshes resume within about 0.1 s of the request ending.
  - What works: a freshly started API, the same code run with fresh pools, or a standalone poller all see changes in 0.5–1.6 s.
  - Not the cause: poll rate, concurrent `/freshness` polling, any single endpoint, or long-held xmin/locks.
  - The root cause is not yet isolated. Evidence: `stall/`.
- **Stream-table drift after a stall (FAIL, rebuild remediates).** Two orders were inserted and then status-updated inside a stalled window. After the catch-up refresh, `st_day_product_status` still counted each order under both its old and new status. The drift persisted after quiescence (oracle 1/2 on shard B).
  - Cause: unproven. A deterministic repro could not exercise the DIFFERENTIAL path, because pause/resume forces a FULL reinitialization and the cost model prefers FULL.
  - Remediation: reinitialization restored 0/0 on both shards. The B-2 `python -m axapi.rebuild` does the same and proves it with the oracle.
  - This is an upstream engine matter: no Rust changes without human approval.
- **G3** remains INCOMPLETE (#28/#41). **10M** has never been run. **B-5** is partial (#38/#39 not deployed). **B-4** is not implemented.

## 4. Fallbacks
- **API or writer stops:** `docker compose -p ax-demo42 -f compose.sharded.yaml up -d api writer` (about 5 s), then reload.
- **Live write stuck:** restart only the API (`… restart api`); a fresh API process measures 0.5–1.6 s. Better: don't demo it; use the §2 numbers.
- **Oracle not 0/0 while the writer runs:** expected lag. Pause the writer (`… stop writer`), wait 10 s, re-run. If it is still nonzero, run the B-2 rebuild for that shard and say so.
- **Docker down:** present the screenshots and saved outputs in this folder.
