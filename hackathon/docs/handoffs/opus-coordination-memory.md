# OPUS coordination memory (persistent project context)

> **Owner:** OPUS. Only OPUS edits this file; Codex and humans communicate through Issue #12.
> **Purpose:** survive context compaction, restarts and new sessions. **Reload at every session start,
> then re-sync from GitHub** (GitHub is the source of truth; this file can be stale).
> **Last updated:** 2026-10-31 ~13:00 UTC by OPUS (Claude Code session on the Opus Mac).

## Session-start checklist
1. Read this file.
2. `git fetch --prune`, then `git worktree list` and `git status` in each worktree.
3. Read Issue #12 comments newer than the "last processed" marks below.
4. Read #19, #20, PR #21 and PR #22 (reviews, inline comments, checks).
5. Diff against this file: new decisions, blockers, ownership changes.
6. Update this file.
7. Resume the highest-priority authorised task (§F).

**Last processed** (do not re-answer):
- #12 up to `IC_kwDOVd5KA88AAAABhgZyLQ` (CODEX P0 audit, 12:46Z) and OPUS 6543601773 (P3 fix STARTED)
- PR #22 reviews up to 12:47:27Z (HUMAN "P0 review correction")
- PR #21 comments up to 12:28:21Z

---

## A. Project overview
- **Hackathon:** Mitigata CyberForge 2026. **Problem statement:** "Multi-Tenant Aggregation Layer" (PRD by Aroop Ghosh, 28 Oct 2026). The reference is `ps_documentation.md` at the repo root; its [PRD] items must be re-checked against the original PRD images, which OPUS has never seen.
- **Mandatory:** FR-1 counts/totals, FR-2 trends, FR-3 Top-N, FR-4 breakdown, FR-5 tenant filter, FR-6 fresh within minutes, FR-7 REST API.
- **Scorecard (Good / Great):**
  - query < 1 s / < 200 ms
  - freshness < 5 min / < 30 s
  - DB safety < 25% / < 10% slower
  - correctness most / all
  - growth < 5× / < 2× at 10M
  - Datasets: 1M/10 tenants and 10M/100 tenants, skewed.
- **Bonus:** B-1 freshness indicator, B-2 rebuild, B-3 per-tenant heavy-query limit, B-4 config metric, B-5 monitoring page.
- **Judge feedback after Round 1:** show real horizontal sharding and behaviour under network partition (→ P3, #19/#20).
- **Architecture:**
  - PostgreSQL 18.6 + upstream **pg_trickle 0.108.3** (Apache-2.0, trickle-labs). Repo source is 0.108.4, which is **not** what runs.
  - Trigger CDC.
  - 3 DIFFERENTIAL stream tables per shard: `st_day_product_status`, `st_day_category_status`, `st_hour_category_status`.
  - Bucket columns are trigger-maintained.
  - FastAPI (`hackathon/app`) with per-shard bounded pools and RLS roles `ax_api`/`ax_writer`/`ax_monitor`.
  - React dashboard (`hackathon/frontend`).
  - Sharded demo: 2 independent PG instances (`compose.sharded.yaml`).
- **Our contribution vs upstream:** schema/stream-table contract, tenant security, API, router/sharding, oracle, measurements and dashboard are ours. The IVM engine is pg_trickle (credited).

## B. Current development state
| Area | State | Evidence |
|---|---|---|
| P1 engine spike | merged #15 | `docs/handoffs/opus.md` |
| API + dashboard (single DB) | merged #18 (c38cd33) as an integration baseline, **not** a judge-ready approval | #18 review checklist still open |
| P3 sharding | PR #22 **HOLD** (review requested follow-up) | `docs/handoffs/opus-sharding.md`, `sharding/results/` |
| PR #22 review fixes | **in progress on `feat/opus-p3-sharding`** (this session) | see §F |
| Frontend PS conversion + new logo | **staged, uncommitted** on local branch `feat/aggregatex-logo` (worktree `~/Downloads/mitigata/AgrregateX-sharding`); 107 files, Revelio product removed. Waiting for the user's OK to commit/PR | lint OK, 3/3 tests, build OK; no browser QA |

**Latest verified results (M1, n=1, REPRESENTATIVE 10k orders total):**
- shard_check 18/18; API vs SQL 200/200.
- Partition (old script revision): A 503 in ~3 s, B 200, no phantom write, recovery ≤ 3 s, A oracle 0/0.
- Latency p50 3.5–5.5 ms; commit→visible p50 ~1.25 s, max 1.85 s.
- **OLTP under dashboard load −52% (FAIL G-3).** Single-DB P1: DIFFERENTIAL −28% tps under sustained writes; IMMEDIATE 0.11 tps.

**Known bugs / limits:**
- Upstream aggregate delta join uses `IS NOT DISTINCT FROM`, so it runs as a nested loop (PROPOSAL P1, untested patch).
- Scheduler stall after drop/recreate.
- `pgt_status().staleness` is wrong while idle.
- No failover/replication.
- No browser QA of the Shards/Engine pages.
- Docker Desktop on the Opus Mac keeps stopping (memory pressure; host swap ~9/10 GiB).

## C. Team coordination
| | OPUS | CODEX (Fedora amd64, 7.5 GiB RAM, ~1.7 GiB avail) |
|---|---|---|
| Owns | `hackathon/app/**`, `frontend/**`, `sql/**`, `sharding/**`, `compose.sharded.yaml`, Opus handoff docs | `hackathon/benchmark/**`, Codex proposals |
| Active PR | #22 `feat/opus-p3-sharding` | #21 `feat/p3-shard-benchmark-tests` (DRAFT, 907c80e; "PR correctness" check FAILURE) |
| Single-writer claims | `partition_demo.sh` → OPUS (claimed on #12 6543601773) | |

- **Humans:** surajgojanur (repo owner, integration reviewer, merges) and shridhar618 (runs this OPUS session).
- **Waiting on others:** HUMAN re-review of #22 after the fixes; CODEX aligning #21 with contract v2 (cookie auth, host-side probes, no curl in the image).

## D. Technical knowledge
- **Image:** `ghcr.io/trickle-labs/pg_trickle@sha256:94344bb9…` is a multi-arch index.
  - arm64 `sha256:e3490ecc…`; amd64 `sha256:92f271e27f8d…08a5`.
  - Both labelled 0.108.3 / PG 18.6-1.pgdg12+2; manifest verified 2026-10-31.
  - Runtime verified **arm64 only**.
- **Sharded stack:**
  - Project `aggregatex-sharded`. API `127.0.0.1:8091`; shard A `:25571`; shard B `:25572`.
  - Networks `_edge` (API/writer, gw_priority 10), `_net_a` (API+writer+shard_a ONLY), `_net_b`.
  - Volumes `shard_a_data`, `shard_b_data`. Login **ON** by default after this session's fix.
- **Single stack:** project `aggregatex`, API `:8090`, DB `:25560`, volume `aggregatex_dbdata`, no-login default (user request).
- **Directory v1:** A = {1,3,4}; B = {2,5,6,7,8,9,10}. Seed 10k global → 5,013 A / 4,987 B. Sequences: A 100M+, B 200M+.
- **API contract v2** (`opus-sharding.md` §5):
  - Cookie `ax_session` auth.
  - 503 `{"shard","retryable"}` + `Retry-After: 5` within ~3 s.
  - `/api/shards` is partial-aware; `/api/engine?shard=`.
  - Live-write visibility is data-based (same-snapshot ST vs raw).
- **Bounds:** connect 2 s; pool wait 3 s; `tcp_user_timeout` 3 s; `statement_timeout` 5 s.
- **Correctness:** `ax.oracle_mismatches()` (EXCEPT ALL both ways), `app/tests/api_oracle.py`, `sharding/tests/shard_check.py`.
- **Safety rules:** never delete volumes or reset DBs; never stop unrelated containers; no 10M without a human OK; no live fault test without the memory gate and a human OK.

## E. Decision history
| Date (UTC) | Decision | Reason | Authorised by | Link | Implemented / tested |
|---|---|---|---|---|---|
| 10-31 | Build on upstream pg_trickle; our contribution lives in `hackathon/` | plan / attribution | HUMAN | #12 kickoff | yes |
| 10-31 | Trigger-maintained bucket columns, not GENERATED | CDC does not capture GENERATED columns; expression GROUP BY forces FULL | OPUS evidence | #15 | yes / tested |
| 10-31 | IMMEDIATE rejected | 0.11 tps | OPUS evidence | #15 | yes |
| 10-31 | Upstream patch P1 (null-safe join) | 900× join cost | **pending HUMAN** | #15 proposal | no |
| 10-31 | OPUS builds the backend API (reassigned from Codex) | user request | HUMAN (shridhar618) | #12 | merged #18 |
| 10-31 | No-login default on the single-DB stack | user request | HUMAN (shridhar618) | #18 | yes |
| 10-31 | #18 merged as an integration baseline | | HUMAN (surajgojanur) | #12 12:19Z | yes |
| 10-31 | P3: two physical shards, directory v1, fail-closed 503, no failover | judges + approved design #19 | HUMAN | #19 | #22 |
| 10-31 | Image comment corrected: multi-arch, not arm64-only | Codex manifest audit, re-verified by OPUS | CODEX + OPUS | #12 12:46Z | yes (this session) |
| 10-31 | Sharded compose login ON by default | review #22 item 2 | HUMAN review | #22 12:37Z | yes (this session) |
| 10-31 | OPUS is the single writer of `partition_demo.sh` | review asked for one writer | OPUS claim | #12 6543601773 | — |

## F. Next actions (ordered)
1. **OPUS:** finish the PR #22 fixes, push, post DONE_WAITING_REVIEW on #12 + PR #22. **Accept:** static + simulated tests pass; docs corrected.
2. **OPUS:** post contract v2 on PR #21 (cookie auth, host probes, ports, A-only network). **Accept:** posted.
3. **HUMAN:** go/no-go for a **live** hardened partition run on a host passing the memory gate (Opus Mac: Docker must be running; Fedora: RAM currently too low).
4. **OPUS:** browser QA of Dashboard/Shards/Engine + outage banner (needs Docker).
5. **OPUS:** commit/PR the frontend PS conversion once the user OKs it (local branch `feat/aggregatex-logo`).
6. **CODEX:** align #21; independent live validation once hardware allows.
7. **HUMAN:** decide PROPOSAL P1 (upstream patch) – the only credible path to the G-3 targets.
8. **OPUS (needs HUMAN approval):** x86_64 CI smoke job. `.github/workflows` is upstream-owned.

## G. Judge Q&A (only verified claims)
- **What problem?** Store dashboards over millions of orders are slow and load the OLTP DB. We maintain small per-tenant summaries incrementally.
- **Why pg_trickle?** In-database incremental view maintenance (IVM) with trigger CDC, so there is no extra service, the data is transactionally consistent, and it is Apache-2.0. **Honest limit:** its aggregate delta join is slow under sustained writes (F3/P1).
- **Tenant isolation?**
  - API: auth before routing; tenant mismatch → 403.
  - DB: FORCE RLS on stream tables and sources; non-owner roles; transaction-local `ax.tenant_id`. A missing tenant returns 0 rows.
- **Sharding?** Two independent PG + pg_trickle instances. A versioned directory maps tenant → shard. The router is in the API connection factory.
- **During a partition?**
  - The cut-off shard's tenants get 503 within about 3 s, and their writes are never redirected.
  - Other shards keep working.
  - Global totals are marked partial, never shown as complete.
- **Unconfirmed writes?** A 503 means "not confirmed". A confirmed commit is never reported as failed (`committed: true` + `visibility_error`).
- **Recovery?** Pools reconnect automatically; demonstrated recovery ≤ 3 s; oracle 0/0 after.
- **Performance?** Reads p50 ~5 ms at 10k. Freshness ~1.2–1.9 s. **DB safety FAILS** (−52% under dashboard load on one laptop). 10M not run.
- **Not implemented:** failover/replication, B-2/B-3/B-4, the 10M run, the upstream patch.
