# G4: signed-event loss in RLS delta staging — correction proposal, not a patch

## Finding and confidence

There is a **statically demonstrable algebraic defect** in the available 0.108.3
release source: RLS staging keeps the first and last event for a source identity,
even when they are both INSERT images. The direct single-table aggregate consumes
both as positive contributions after the cancelling DELETE has been discarded.
This produces exactly the Fedora **paid + cancelled** result from an ordered
`I(paid), D(paid), I(cancelled)` history.

The rule is mathematically wrong for a direct signed-event consumer. Its text is
also embedded in the installed runtime binary, and live catalog SELECTs confirm
source RLS is enabled and forced. These facts strongly support this mechanism
as a Fedora explanation. They do **not** reconstruct its missing historical
buffer contents or prove this precise path ran for order 100000000.

The same ordered history does **not** produce Mac's **paid-only** result under
this rule. Do not assert one proven explanation for both observed variants.
No upstream patch, refresh, mitigation setting or data repair was performed.

## Runtime/source relationship

| Evidence | Result |
|---|---|
| Runtime extension / OCI version | 0.108.3, image index `sha256:94344bb98995b19c826f939739672481abaab8c25710e3910b48bdb7cf5b3b8d` |
| Available upstream release tag | `v0.108.3` at `ce709f06327b4801f79fc48934bc96107b450907` |
| Tag Cargo.toml | version 0.108.3 |
| AgrregateX main | `c19b89a24370d29412fc42c250a86b0ea68f791f`, Cargo.toml 0.108.4 |
| Installed pg_trickle.so SHA256 | `7d22f093dc0841d06f0738f32ba93f06213279e6a66994dfe1bdda8cfa84b1bf` |
| OCI source revision label | absent; exact whole-binary build commit NOT established |
| `src/refresh/delta_stage.rs` tag vs main | byte-identical SHA256 `2e8f74250d673214e05ff9535f4ad56109824254634193e6800eb5f50e808c65` |
| Other CDC/DVM/merge files | substantial differences; full equivalence NOT claimed |

Fetched release source via Git from the upstream repository named in Cargo.toml.
`version-evidence.json` records file hashes and selected runtime binary strings,
including the defective first/last predicate and RLS-stage action filter.
Image labels and a version number alone are not reproducible-build provenance.
Relevant text equivalence is stronger than assuming current-main behavior, but
does not prove every surrounding compiled branch matches the tag.

`runtime-capture-definition.txt` contains only catalog output for RLS flags and
the installed UPDATE trigger definition. It confirms flat D/I images, stable
`SCAN_KEY(tenant_id,order_id)` identity, and separate old/new payloads. No business
rows, credentials or database dump were captured in this phase. The sole database
interaction used BEGIN READ ONLY, a 2s local timeout, two SELECTs and ROLLBACK.
Reading the existing container's shared library did not alter it.

## Source call path (release-tag line numbers)

Links below refer to upstream **0.108.3**, not the newer AgrregateX snapshot.

| Stage | Actual entry/function | Behavior relevant here |
|---|---|---|
| Capture | [`create_change_trigger` region / `build_stmt_trigger_fn_sql`](https://github.com/trickle-labs/pg-trickle/blob/ce709f06327b4801f79fc48934bc96107b450907/src/cdc/mod.rs#L2427) | Statement AFTER triggers use transition tables. INSERT emits I(new); UPDATE emits D(old) and I(new), same statement LSN. `change_id` supplies event ordering. Both images have the same source identity when tenant/order PK is unchanged. |
| Refresh dispatch | [`execute_differential_refresh_with_tuning`](https://github.com/trickle-labs/pg-trickle/blob/ce709f06327b4801f79fc48934bc96107b450907/src/refresh/merge/mod.rs#L718) | Uses previous/new source frontiers, optional persistent compaction, then stages source windows before owner execution. |
| Persistent compaction | [`compact_change_buffer`](https://github.com/trickle-labs/pg-trickle/blob/ce709f06327b4801f79fc48934bc96107b450907/src/cdc/mod.rs#L1406) | Same endpoint-removal formula; threshold/advisory-lock gated. This tag admits nondeferrable PK sources with only one dependent stream. The orders source has three dependents, so this tag's guard excludes it. Do not blame that branch without runtime evidence. Other reducer copies warrant audit. |
| Privileged stage | [`DeltaStage::prepare` → `stage_source`](https://github.com/trickle-labs/pg-trickle/blob/ce709f06327b4801f79fc48934bc96107b450907/src/refresh/delta_stage.rs#L79) | Copies the bounded LSN window into a per-stream temporary relation. For RLS sources, ranks by source identity/change_id, removes interior events and I→D histories, then checks current owner-visible source identities. This temporary-stage compaction is not threshold gated. |
| Source override | `DeltaStage::source_tables`, DVM staged generation / context | Binds generated scans/direct aggregates to the staged relation. Cache-miss DVM generation is in merge/mod.rs around 2050; cached templates must use the same source substitutions. |
| Product aggregate | [`diff_aggregate` → `is_direct_agg_eligible` → `generate_direct_agg_delta`](https://github.com/trickle-labs/pg-trickle/blob/ce709f06327b4801f79fc48934bc96107b450907/src/dvm/operators/aggregate.rs#L1844) | Plain Scan→GROUP BY, COUNT and simple SUM qualify for P5. Bypasses `diff_scan`; counts/sums staged I and D images directly by tenant/day/product/status. |
| Joined aggregates | [`diff_scan_change_buffer`](https://github.com/trickle-labs/pg-trickle/blob/ce709f06327b4801f79fc48934bc96107b450907/src/dvm/operators/scan.rs#L202), join differentiation, then standard aggregate | Joins are not P5-eligible. Standard keyed scan emits earliest old D if the row existed before, and latest I if it exists afterward; it can remove the redundant first I left by staging. Join snapshot/cross terms must also be checked in a controlled test. |
| Group state | [`diff_aggregate` group merge](https://github.com/trickle-labs/pg-trickle/blob/ce709f06327b4801f79fc48934bc96107b450907/src/dvm/operators/aggregate.rs#L2104) | New count = old count + inserts − deletes; sum and nonnull auxiliaries updated analogously. Empty grouped state emits D. Scalar aggregates have separate empty-input semantics. |
| Group identity | aggregate.rs around 2050–2100 | Encodes complete group keys with GROUP_KEY domain and reuses existing target identity where found. Paid and cancelled are distinct group identities; source-row PK identity is not aggregate identity. |
| Final apply | [`build_merge_sql`](https://github.com/trickle-labs/pg-trickle/blob/ce709f06327b4801f79fc48934bc96107b450907/src/refresh/codegen.rs#L2247), merge/mod.rs around 2630/3160 | MERGE deletes D, updates matched I, inserts unmatched I. PH-D1 DELETE+INSERT removes affected delta IDs then inserts surviving I state. Both faithfully apply an already-wrong delta. Mac/Fedora history reports `delete_insert`; strategy name does not identify the defective producer. |

The optional vector aggregate producer in merge/mod.rs must be recorded in the
controlled trace as another staged-event consumer. It does not make retaining
two positive source images algebraically valid. Do not infer its activation from
eligibility or a GUC default alone.

The actual stream definitions are `hackathon/sql/10_stream_tables.sql`: product
is Scan→Aggregate, category/hour are Join→Aggregate. Oracle SELECTs in
`hackathon/sql/30_oracle.sql` recompute from independent raw orders/products.

## Exact invariant violation

For a stable keyed row, before-window absence and after-window cancellation:

| Ordered event | Group | Signed count / units / cents |
|---|---|---|
| I, original insertion | paid | +1 / +1 / +14094 |
| D, UPDATE old image | paid | −1 / −1 / −14094 |
| I, UPDATE new image | cancelled | +1 / +1 / +14094 |

Correct sum: paid zero; cancelled +1/+1/+14094. The release reducer removes rows
when the sequence starts I and ends D, or when both ascending and descending
rank exceed one. For the three events above it removes **only D(paid)**.
Staging now contains I(paid) + I(cancelled). Current-source visibility checks
compare source PK identity, not status payload: both inserts refer to the same
still-visible order, so both survive. The P5 aggregate emits two positive groups.

This error occurs **before direct aggregate delta generation**, in preparation of
its signed input. Empty-group deletion and final apply cannot recover a negative
contribution that was erased. NO_DATA refreshes do not reconcile arbitrary old
target rows, explaining persistence after buffers drain.

`offline-model.json` records ten pure-Python signed-event cases. The release
predicate reproduces Fedora's both-statuses outcome; the proposed reducer matches
raw signed arithmetic in all ten modeled cases. This is not PostgreSQL/Rust
execution, proof of every aggregate, or a controlled reproduction on the binary.

## Mac paid-only versus Fedora both-statuses

For the exact ordered three-image input above, this source rule predicts **both**
statuses, not paid only. Thus Mac's claimed same-delta history is not enough to
prove this mechanism produced its final state. The recorded 0.3-second gap and
25-second wait do not prove both commits occupied the same materialized frontier:
the scheduler may already have captured a bound before either query finishes.
Its raw output proves wrong final data, not the intervening event/stage sequence.

Potential distinctions needing captured evidence: previously materialized paid
state; exact source buffer ordering/LSNs; incomplete frontier window; visibility
filtering; another producer/cache/runtime revision; or loss during application of
an otherwise correct aggregate delta. A reversed/lost UPDATE image could also
break endpoint assumptions, but no capture establishes that here. UNION ALL
branch order is not a substitute for verifying generated event order.

Fedora's lost historical CDC images mean causation remains uncertain despite an
exact static mechanism matching its result. PR #49's FULL repair supports an
incremental-path problem, not a particular line of Rust or equivalence of variants.

## Option 1 — proposed differential correction

For the admitted **immediate, nondeferrable stable-PK** shape, normalize each
ordered source-identity history to its true before/after boundary:

| First / last actions | Keep |
|---|---|
| I / I | latest I only |
| I / D | nothing |
| D / I | earliest D and latest I |
| D / D | earliest D only |

Pseudocode for the intended retained-row predicate:

```text
keep = (ascending_rank == 1 AND first_action == D)
    OR (descending_rank == 1 AND last_action == I)
```

A single I/D is retained once. This preserves complete before/after payloads,
including status/product/date movement, amount changes, delete/reinsert and an
empty group. Narrowest candidate: correct the reducer inside
`DeltaStage::stage_source` before visibility pruning, with a documented keyed
admission boundary. Audit/share the invariant with the persistent and partitioned
compaction helpers before claiming a general engine repair. Do not blindly apply
first/last netting to keyless multiset sources or deferred-uniqueness histories.

Regression risks: deleting intermediate events needed by consumers; misordered
change IDs under concurrency/sequence caching; primary-key changes becoming two
identities; source visibility transitions under RLS; old/new tenant visibility;
shared consumers with different frontiers; cache invalidation; keyless duplicate
multiplicity; non-COUNT/SUM auxiliary state. Preserve capture atomicity and the
original frontier range. Do not disable RLS or drop filtering as a performance fix.

An alternative candidate is to route the direct aggregate through a proven keyed
normalizer rather than consume endpoint pairs as independent signed events. That
changes a wider query-generation/performance surface and requires the same tests.
Merely disabling P5 can leave vectorized/other consumers or compaction copies
exposed. Retaining all raw events without fixing visibility pruning is also unsafe:
an insert-delete history can lose only its now-invisible insert and leave an
unmatched negative event. No speculative patch is justified without the trace below.

Even a correct reducer prevents future drift; it does **not** remove already
materialized ghosts. Existing-data repair needs a separately authorized full
reconciliation/repair and post-repair oracle, never a silent rebuild during analysis.

## Options 2 and 3 — containment and judge policy

| Option | Correctness boundary | Performance / safety tradeoff |
|---|---|---|
| FULL on affected table | Teammate's disposable run repaired/recomputed the group and passed its oracle; independently verify in the exact target/config before use. Other tables still refresh independently. | Reported 5.8s vs 3.3s: +2.5s, ~76% more duration for this refresh, not a measured OLTP regression. More scans/WAL/I/O can worsen G3 and scheduler contention. A 1s requested cadence cannot imply 1s visibility. G2 needs fresh measurements; G1 queries still use rollups but contend with heavier refreshes. No 1M/10 PASS inference. |
| Explicit all-source API mode | Recompute each requested answer from raw orders/products under the existing tenant authorization/router and transaction-local RLS setting. One consistent request snapshot; no rollup/source stitching for affected answers. | Repeated scans may materially raise 1M HTTP latency and OLTP cost. Current 1k timings do not bound this. Use bounded queries/timeouts and fail closed on unavailable shards; never return partial totals as complete. Clearly expose maintenance-bypass/degraded mode and retain G4 incident evidence. |

Verified category aggregates can supply counts/sales/category/hour metrics only
at their dimensions and refresh states; they cannot reconstruct product Top-N.
Silently combining them with raw product queries or the broken product stream
risks internally inconsistent results. Prefer one explicit all-source mode for
all four families when correctness across a dashboard is required; separate HTTP
requests still have separate snapshots unless an explicit snapshot protocol exists.

**Safest judging choice:** until a reviewed containment is separately implemented,
disclose/omit known-wrong KPI/Top-N/status results and the live-write scenario;
do not call this working dashboard correct or hide the incident by choosing an
unaffected date. For this small preserved demo, a visibly labelled, fully raw-source
read mode is a narrower correctness-first application proposal than deploying an
unverified engine binary. It still needs app-owner review, tests and authorization;
it is not implemented here. FULL is a practical separately approved disposable
mitigation candidate, with explicit measured maintenance cost, not the long-term fix.

Long-term: repair differential normalization, validate signed-delta invariants,
then explicitly repair existing drift with evidence retained. Differential remains
the preferred architecture once correctness is proven. No G1/G2/G3 target can be
awarded from these mitigation estimates.

## Deterministic regression specification (PROPOSED, not executed)

Use a tiny isolated fixture, composite `(tenant_id,order_id)` PK, forced source
RLS and a stream owner matching the problematic setup. Define all three original
streams. Use unique product/day/hour/category keys to avoid accidental existing
groups; include another tenant as a negative isolation control. Each row has one
unit/1000 cents unless stated. Repeat with RLS off/on only in the disposable
fixture, never by changing the preserved demo's policies.

Control refresh windows explicitly: create fixtures with scheduling disabled or
long cadence under separately approved test controls, establish the baseline,
perform committed mutations, record buffer windows, then invoke exactly one
test refresh. Sleeps alone are not synchronization. Across-delta cases must prove
the first completed refresh/frontier consumed the insert before the next update.

| Case | Source expectation at final snapshot | Additional required assertion |
|---|---|---|
| Insert paid → cancel, same delta | one cancelled/1/1000; paid absent | stage and P5 signed paid delta zero; tests the primary defect |
| Insert paid → cancel, separate deltas | first paid/1/1000, then cancelled/1/1000 only | first oracle exact before next commit; second delta D(paid)+I(cancelled) |
| Existing paid, two updates same delta | final cancelled only | old paid removed, no shipped residue |
| New paid → shipped → cancelled | final cancelled only | cancel intermediate paid/shipped images; distinguish absent-before from existing-before |
| Group-key movement | final product/day/status and mapped category/hour only | move across midnight/product/category; old group gone, unchanged tenant isolated |
| Existing-row deletion | no group when sole row deleted | emit group D; no zero-count physical row |
| Insert and cancel in one window | cancelled remains; this is not a delete | paid has zero sales; cancellation is retained source data |
| Insert then delete / group empty | no source row, no stream group | I→D disappears; existing update→delete keeps only initial D |
| Two orders sharing a group | counts/units/cents sum both final states | row identities must net separately before group combination; include one cancel/one paid and both cancel variants |
| Fedora both-statuses variant | clean baseline + ordered three images → cancelled only | unpatched capture should show Ipaid/Icancel stage and two product groups if this mechanism is active; joined oracles exact |

For **every row** in this table, after test-controlled quiescence and recorded
frontier completion, run the exact three-table symmetric EXCEPT ALL SELECT body
from `hackathon/sql/30_oracle.sql` in one REPEATABLE READ READ ONLY snapshot.
Require each named table present, separate missing/extra counts **0/0**, no extra
zero-count groups. Use independently recomputed UTC timestamps and integer-cent
arithmetic. Compare target customer API fields as a separate assertion, not as
the source oracle. Include MERGE and DELETE+INSERT variants; fix must survive both.

Also test a deliberately **pre-existing dirty target** with both statuses on a
disposable fixture: no-change differential refresh is not expected to heal it.
This distinguishes prevention from separately authorized repair; never relax the
oracle to hide historical drift. Add keyless/deferred-PK and RLS visibility-change
cases before broadening the admission contract beyond the narrow keyed fix.

Existing evidence: Mac PR #49 reports 5 deterministic failures and a FULL repair;
Fedora PR #48 has five read-only persistent snapshots and six targeted GETs.
Existing source tests cover direct aggregate eligibility/SQL generation, CDC
sequence CACHE=1, and several RLS mutation paths (`tests/e2e_cdc_tests.rs`,
`tests/e2e_rls_tests.rs`). Their presence is not proof this full combination passed;
they were not rerun here. The 25 benchmark tests and ten algebra models are offline
checks, not extension regression qualification.

## Controlled test that distinguishes the remaining hypotheses

Approval request: a **small disposable reproduction only**, not a scale run or
engine patch. Proposed Fedora project `ax-issue31-g4-repro`, fresh volume
`ax-issue31-g4-repro_data`, DB loopback 25634, optional API 18134;
pin the existing 0.108.3 image digest, <=1GiB DB/256MiB API/one CPU, <=100 orders,
10-minute ceiling. Require >=4GiB available host RAM, >=5GiB persistent disk,
no sustained swap I/O, exact container/volume ownership review and no active peer
experiment. Current memory-pressured Fedora is not cleared for this target.
An existing teammate target requires that owner's explicit coordination/approval.

On that target capture, **before cleanup**, for a known empty group and for an
already materialized paid group: ordered CDC `change_id/LSN/action/identity/payload`,
previous/new frontier and transaction visibility, temporary stage rows, generated
P5 vs scan/join SQL and final aggregate delta, applied strategy, and source/target
before/after. Use existing diagnostic facilities where sufficient; any temporary
instrumentation or build needs a separate reviewed scope, not an implicit Rust fix.

Decisive observations:

1. Raw Ipaid/Dpaid/Icancel → stage Ipaid/Icancel → delta two positive groups:
   staging mechanism confirmed for the Fedora variant.
2. Stage correct, aggregate delta wrong: investigate producer/cached template.
3. Delta correct, target wrong: investigate apply identity/DELETE+INSERT/frontier.
4. Raw images/order/window differ: investigate capture, ordering, commit-bound
   selection and the Mac same-window assumption before changing aggregation.

Only after that trace: request explicit authorization to patch the narrow reducer
and add the specified extension tests on an isolated branch; run relevant unit,
integration/E2E tiers plus `just fmt`/`just lint`. No repair/deployment of the
preserved database is included. This proposal leaves PR #48 draft and #31 open.
