# Controlled runtime reproduction — PREPARED / BLOCKED, NOT EXECUTED

No disposable database was started. No mutation, refresh, setting change or
query was issued against the preserved Fedora database or APIs in this turn.
No Mac resource, source Rust or application file was changed. Historical evidence
remains separate. The runtime classification for this requested experiment is
**INCONCLUSIVE: required intermediate observations were not collected**.

## Gate observations

Fetched main remains `c19b89a24370d29412fc42c250a86b0ea68f791f`;
PR #48 remote branch matches local `d049da665b7999f4400ea3b249213b79380a1b5b`;
PR #49 source branch remains `5c8580b62f4738e22709b24c3e5f7c2053fd8cba`.
Issue #31/#12 and both PR discussions were reread. Existing worktrees/untracked
files were retained; only this new evidence/preparation directory is staged.

The observed host has about **1.17 GiB available RAM**, below the required 4 GiB.
Swap used about 5.56 GiB; interval vmstat samples include swap-in 1572 KiB/s,
swap-out 6764 and 12300 KiB/s. The first vmstat row is an average since boot;
the interval rows independently demonstrate current swapping. Persistent /home
has about 227 GiB free, exceeding the 5 GiB gate. See current `preflight.json`
and raw memory/disk/swap observations; values fluctuate between captures.

No matching project/container/volume/network name or port 25634/18134 listener
was observed. Two existing PostgreSQL/API stacks and other services remain.
Names do not prove absence of another workload; competing-benchmark exclusion
still requires operator/owner confirmation. No such confirmation was inferred.

Cached pinned image is linux/amd64 on this x86_64 host; labels identify PostgreSQL
18.6 and pg_trickle 0.108.3. Multiarch index is
`94344bb98995b19c826f939739672481abaab8c25710e3910b48bdb7cf5b3b8d`,
local platform digest `92f271e27f8d3b9b5aaf568df10ee377937f48d79825e73adaf469768b0208a5`.
This phase did not start a container to query server versions. Previous runtime
version/source-build uncertainty remains documented in the earlier proposal.

The user instructed a separate explicit target approval gate; no affirmative
target-specific approval has been supplied. The resource failure independently
prohibits launch, even if approval is later supplied. **Do not free memory by
stopping the demo or someone else's services.**

## Prepared artifacts and bounded target

- `compose.yaml`: project `ax-issue31-g4-repro`, container
  `ax-issue31-g4-repro-db`, fresh volume `ax-issue31-g4-repro_data`, default
  project network `ax-issue31-g4-repro_default`, only loopback DB port 25634.
  No API service is needed; port 18134 remains reserved but unused.
- DB budget 1 GiB, one CPU, 128 MiB shared memory, no restart policy;
  PostgreSQL starts with pg_trickle.enabled=off **only in this proposed stack**.
  Source inspection indicates this stops scheduler work while manual refresh
  remains callable; this compatibility must be verified at startup or abort.
- `fixture.sql`: original schema/bucket/security/three stream definitions reused
  via read-only mounts, not copied/reimplemented. Synthetic 80-order baseline,
  explicit composite PK, forced source/stream RLS, superuser stream owner matching
  the problematic admission path. Original read-only API role is created only
  inside this future fixture. Distinct database `ax_g4_repro`; scripts refuse
  `aggregatex` and an enabled scheduler before any changes.
- `cases.sql`: deterministic Case A and split Case B phases; separate explicit
  commits, no sleep. Final two principal cases add two orders (82 total).
- `trace_refresh.sql`: one connection and explicit transaction captures raw
  buffer before refresh, frontier before/after, post-staging and materialized
  aggregate rows before COMMIT, selected target rows, and actual history strategy.
  Missing internal tables produce an explicit blocker and rollback/exit 4.
- `oracle_select.sql`: independent three-table EXCEPT ALL SELECTs, one read-only
  consistent snapshot, no installation of helper functions.

These are preparation artifacts, **not executed or runtime-qualified scripts**.
Their guards reduce accidental targeting risk but do not replace host/container
identity checks or human approval. No automatic launch runner is supplied.

## Execution-ready approval packet

Approval requested for exactly this target, <=100 orders, <=10 minutes including
bootstrap and capture, DB <=1 GiB/one CPU; no API planned. Require a fresh preflight
with >=4 GiB available RAM, >=5 GiB persistent free disk, no sustained swapping,
confirmed no competing benchmark, exact unused ports/resources, unchanged pinned
image identity and explicit exclusive owner. If any check fails, do not launch.
Keep data/evidence on failure. Only owned disposable-container stop is within the
proposed end-of-run lifecycle; no volume/network deletion or demo operation is included.
An external 10-minute controller deadline must be set before startup; never let
the controller's deadline stop an existing container selected by a partial name.

After approval AND passing preflight, from this directory, inspect compose with
private environment provisioning. Do not publish rendered compose environment.
Use a private throwaway `AX_G4_SUPERUSER_PASSWORD`; never include it in commands,
logs, evidence or commits. The following launch commands are **gated instructions**:

```bash
# Only after the operator's recorded approval and a fresh PASS preflight:
docker compose -p ax-issue31-g4-repro -f compose.yaml up -d db
docker inspect ax-issue31-g4-repro-db --format '{{.Name}} {{.Image}} {{json .Config.Labels}} {{json .NetworkSettings.Ports}}'
docker exec ax-issue31-g4-repro-db psql -X -U postgres -d ax_g4_repro -v ON_ERROR_STOP=1 -f /protocol/fixture.sql
docker exec ax-issue31-g4-repro-db psql -X -U postgres -d ax_g4_repro -v ON_ERROR_STOP=1 -f /protocol/oracle_select.sql
```

Before mutations, verify exact container image/labels and mounted fresh volume,
server/extension versions, disabled scheduler, source/stream owners and RLS,
all streams populated with nonempty frontiers, no needs_reinit and oracle all0/0.
Check no scheduler-initiated history growth while no manual command is running.
A FULL/schema reinit/fallback during the principal test invalidates differential
coverage; retain the result and abort classification. Initial baseline bootstrap
FULL/reinit records are recorded separately. Avoid interpreting NOTICE-skipped
manual refresh as an executed DIFFERENTIAL refresh.

### Case A — absent before window

Recommended first attempt order is **B then A** in this fresh fixture: B has an
independent paid baseline and should pass under the candidate staging mechanism;
A can then expose the defect without contaminating B's initial global oracle.
If B fails, preserve it and stop; do not reset the fixture to obtain an A PASS.

1. Save baseline frontiers/source/streams, and all0/0 oracle. Prove product1/day
   2026-11-20 absent; no background writer/scheduler work.
2. Execute `cases.sql` with `-v phase=A`, recording COMMIT returns and exact source
   rows after both transactions. Its INSERT and UPDATE use order1001.
3. Execute `trace_refresh.sql` with `-v stream=st_day_product_status -v strategy=auto`
   as one psql invocation, retaining full stdout/stderr. Do not autocommit the
   refresh before temp-table inspection. Capture logs bounded by test PID/times.
4. Filter externally saved raw rows using **that refresh's exact** previous/new
   orders LSN bounds. Require ordered Ipaid,Dpaid,Icancelled all in `(prev,new]`,
   with correct identities/payloads. A global pre-refresh WAL position or elapsed
   sleep is insufficient. If any event lies outside, classify capture/frontier
   difference; do not call it the intended same-window test.
5. Confirm latest history identifies this command as completed DIFFERENTIAL,
   no fallback, actual strategy delete_insert; then inspect joined tables in
   separate manual captures, preserving their own frontiers. Save post-commit
   source/target/oracle. Require source cancelled only, paid absent in expectation.

### Case B — already materialized paid

Case A may leave drift. Do not repair it just to pass Case B. Preserve the global
oracle failure and restrict B's causal expectations to its unique key; full clean
oracle acceptance for B requires a separately approved fresh fixture/run. Prefer
separate fresh owned target lifecycle/volume approval for independent repetitions.

1. `cases.sql -v phase=B_setup` inserts order1002, product2/day2026-11-21, paid.
2. Capture/refresh all three; prove this exact paid row is materialized as1/1/1000,
   with consumed frontier >= its insertion LSN. Record any unrelated Case A drift.
3. `cases.sql -v phase=B_update` commits cancellation. Before/after trace must
   prove raw Dpaid,Icancelled are both in B's consumed window.
4. Expected aggregate change: D of sole paid group, I cancelled/1/1000. Compare
   all three complete streams with the independent oracle and report all residual
   mismatches, distinguishing prior A contamination from new B behavior.

Repeat clean A and B for MERGE using `strategy=merge`, with GUC
aggregate_fast_path=off as prepared. For DELETE+INSERT use auto and threshold1.0
against the analyzed 80-group fixture. The obsolete literal strategy
`delete_insert` is **not** a forcing mechanism in the available release source.
Actual history/trace must prove the path; if auto chooses another path, mark
DELETE+INSERT untested. Repetition/fresh-volume targets require approval, not
automatic resource recreation or silent fixture resets. All attempts share the
100-order/10-minute cap unless explicitly re-budgeted.

## Diagnostics: observed versus inferred boundaries

The release uses temporary source stages with ON COMMIT DROP and no explicit
drop at `stage_source` exit. The materialized PH-D1 delta similarly appears to
survive until COMMIT. Same-backend inspection after manual refresh may therefore
capture actual **post-filter** stage and applied aggregate delta without Rust
changes. This is a source-supported experiment design, not a verified runtime API.

Existing `log_delta_sql=on` emits at DEBUG1; log_merge_sql emits a template.
Set isolated session/server logging accordingly and correlate PID/pgt_id/frontier.
A template is not proof that its DML executed. In the disposable environment only,
inspect whether existing auto_explain is installed: nested-statement actual plans
may establish executed SPI commands and affected rows. Do not install extensions,
LOAD modules, add table triggers, or build Rust without recording that diagnostic
scope and obtaining any additional approval. A trigger observer can change apply
strategy, so it cannot establish the original MERGE/PH-D1 path.

Raw_before is an external copy of source buffer events, not an observed internal
pre-compaction stage. The post-stage diff alone cannot separate compaction from
visibility pruning with certainty. Missing stage boundaries or executed-operation
trace must stop the corresponding subtask; see STAGING_TRACE.md and
AGGREGATE_DELTA_TRACE.md for the minimum additional instrumentation request.

## Offline regression plan

All expectations below are signed count/units/cents for one unit/1000 cents;
group keys include tenant, UTC bucket and product/category/status as appropriate.
Run every case with forced RLS and both actually observed apply strategies; RLS-off
is a disposable control only. Use disjoint keys and controlled refresh boundaries.

| Case | Required signed aggregate change / final source |
|---|---|
| Insert→cancel same delta | paid net0; cancelled +1/+1/+1000 |
| Insert→cancel separate deltas | first paid+1, then paid−1 and cancelled+1 |
| Existing paid update | paid−1, cancelled+1; old group deleted when sole row |
| New paid→shipped→cancelled | paid/shipped net0, cancelled+1 |
| Existing paid→shipped→cancelled | paid−1, shipped net0, cancelled+1 |
| Product/day/hour/category movement | old key−1, final key+1 with independently joined category |
| Insert→delete | net0, no persisted group |
| Existing update→delete | original key−1, intermediate key net0, group absent |
| Two rows sharing group, cancel one | paid count/units/cents2→1, cancelled0→1 |
| Two rows sharing group, cancel both | paid2→0, cancelled0→2, paid group removed |

For each, execute `oracle_select.sql`: require three named tables, missing0/extra0
after test-controlled quiescence; also assert each expected per-group delta before
application. Group becoming empty must disappear, not remain with count0. Require
source/control-tenant counts and bucket/cents arithmetic unchanged. Include current
Fedora both-statuses and Mac paid-only outputs as distinct failure classifications.

No mutation regression was executed. Existing 25 benchmark/acceptance tests and
offline bundle/oracle checks are recorded in validation.txt; they do not verify
the prepared SQL against PostgreSQL. Rust fmt/lint availability is recorded honestly.
