# Runbook (issue #67)

**Nothing below P0 runs without explicit human approval of that phase**, naming the environment, budget and commands. Never touch Fedora `round1-db`, `127.0.0.1:8093/8094`, the preserved `aggregatex` demo (:8090), `ax-demo42`, or volumes that aren't listed. Run from `hackathon/`.

## Global stop rules (abort the phase, keep the evidence, mark it NOT QUALIFIED)
- Mac swap free < 512 MB, or `memory_pressure` reports "critical".
- Docker unresponsive for > 30 s, or any container OOM-killed.
- Disk free < 8 GiB.
- HTTP 5xx > 1 % of requests in a phase.
- Wall time over budget.
- For mutating phases: any write that isn't to the phase's own disposable project.

**Rollback:** `docker compose -p <phase project> … stop`. Volumes are deleted **only** with explicit approval naming them.

## P0: preflight (read-only, every phase)
```bash
sysctl -n vm.swapusage; memory_pressure | tail -1; df -h ~ | tail -1
docker info --format '{{.MemTotal}} {{.ContainersRunning}}'; docker ps --format '{{.Names}}'
```
Proceed only if swap free > 2 GB, Docker VM ≥ 3.8 GiB, and no other heavy stack is running (stop the user's stacks only with approval).

## P1: G4 patched runtime (BLOCKED on resources + approval)
- **Budget:** a pgrx release build of PR #58. **Use a different host (Fedora or CI) because the 8 GB Mac is too small.** The disposable target is `ax-issue54-fix` (≤ 2 GiB, ≤ 30 min).
- **Steps:**
  1. Build the image from `fix/opus-54-net-change-reducer` @ `cd6aed0`, and record its digest.
  2. Run `compose.yaml` with `AX_PG_TRICKLE_IMAGE=<digest>`, a 10k seed and `-p ax-issue54-fix`.
  3. Run TEST_PLAN §A cases A1–A15 and record `pgt_refresh_history`.
  4. Run `ax.oracle_mismatches()` and `app/tests/api_oracle.py`.
- **Pass** = every case 0/0, with no FULL refresh or reinit during a case.
- **Rollback:** stop the project. No deployment to any existing stack.

## P2: B4 live (approval needed; ~1.4 GB cap, ~10 min)
```bash
S=<scratchpad>/b4-override.yaml   # api/writer image -> aggregatex-b4:local (keeps the shared tag untouched)
AX_API_PORT=18291 AX_SHARD_A_PORT=25771 AX_SHARD_B_PORT=25772 AX_SEED_ORDERS=4000 \
  docker compose -p ax-b4test -f compose.sharded.yaml -f $S up -d --build --wait
python3 -I app/tests/live_b4_check.py ax-b4test 18291 25771 25772
docker compose -p ax-b4test -f compose.sharded.yaml stop
```
Run it from the PR #66 worktree.

## P3: G2 freshness at 1M (approval needed; reuses volume `ax-scale-1m_scaledata`, no reload)
- **Budget:** ≤ 1.5 GiB, ≤ 60 min.
- **Steps:**
  1. Start the stack: `docker compose -p ax-scale-1m -f compose.scale.yaml up -d`.
  2. Run the probe harness (TEST_PLAN §C; to be written as `scorecard_mac/freshness_probe.py` after approval) at idle, 5, 20 and 50 writes/s.
  3. Stop the step-up at the first rate where > 10 % of probes time out.
- **Note:** this phase **mutates** the 1M fixture. After it, the fixture's oracle state is recorded and the fixture is **not** reused as a clean G1/G5 baseline without B-2 rebuild approval.

## P4: G1 at 10M (approval needed; reuses volume `ax-scale-10m_scaledata`, read-only HTTP)
- **Budget:** DB container 2 GiB, ≤ 45 min.
- **Steps:**
  1. Start the stack and stop the writer (read-only measurement).
  2. Run `integration/scale/http_latency.py --n 200 --warmup 10`. A raw-sample and concurrency option needs a small harness change, prepared after approval.
  3. Run `EXPLAIN (ANALYZE, BUFFERS)` of the worst scenario as `ax_api` with `ax.tenant_id` set.
- **Stop rule:** the 10M DB uses about 1.2 GiB resident. On this Mac P4 runs **alone**: no other stack running.

## P5: G5 recompute (no new load if P4 has run; P4-equivalent 1M run needs approval)

## P6: G3 (BLOCKED on this Mac)
Host freezes already confounded the 10k run here. It needs a resourced host and a separate client. The procedure is TEST_PLAN §D. Owner: Codex/Fedora under #31, unless the operator assigns otherwise.
