# #54: pg_trickle CDC reducer fix (design and regression plan; P0, no code change)

**Status:** design only. No Rust changed, no container started for this document, no data repaired.
- **Runtime evidence** is from #50 (PR #52) and the Mac 1M/10M runs (#49, 10M PR).
- **P1 (implementation and disposable runtime tests) needs separate human approval**: see §8.
- **#31 G4 stays FAIL until P1 is proven.**

## 1. Source / binary provenance (#54 P0-1)
| Item | Finding | Basis |
|---|---|---|
| Running binary | PostgreSQL 18.6 + pg_trickle **0.108.3**, image index `sha256:94344bb9…` (arm64 `e3490ecc…`, amd64 `92f271e2…`) | `SELECT extversion`, `docker inspect` |
| Upstream source | tag **`v0.108.3` = `ce709f06327b4801f79fc48934bc96107b450907`** (`trickle-labs/pg-trickle`) | `git ls-remote` + shallow clone of the tag |
| Repo snapshot | `Cargo.toml` says 0.108.4 (commit `24fb2f4`) | file |
| `src/refresh/delta_stage.rs` | **byte-identical** between the v0.108.3 tag and the repo snapshot | `diff` |
| `src/cdc/mod.rs` | differs (347 lines). Both versions contain the same reducer predicate and the same D-before-I capture order | `grep` on both |
| Limit | Tag ≡ shipped binary is assumed, not proven: there are no reproducible build hashes. The runtime trace (#50) matches the tag's SQL exactly, which supports equivalence | §2 |

## 2. Failure boundary (#54 P0-1, closing #50's open question)
`DeltaStage::stage_source` (`delta_stage.rs:79`) builds `pg_temp.__pgt_cdc_<pgt>_<src>` from the raw window. For **RLS** sources it then runs, in order:
1. **The reducer** (`delta_stage.rs:149-168`):
   `DELETE … WHERE (first_act = 'I' AND last_act = 'D') OR (rn_asc > 1 AND rn_desc > 1)`, partitioned by `__pgt_row_id`, ordered by `change_id`.
2. **The visibility filter** (`filter_sql`, `delta_stage.rs:134-141`): `DELETE … WHERE c.action <> 'D' AND NOT EXISTS (owner-visible source row)`.

**The visibility filter cannot delete a `D` row** (`c.action <> 'D'`). In #50 the lost event was a **`D`** (change 6), so the **reducer is the only statement in staging that can remove it**. Evaluated on #50's three events for order 1001 (`I` cid 5, `D` cid 6, `I` cid 7), the reducer marks cid 6 interior (`rn_asc = 2, rn_desc = 2`) and deletes it, keeping cids 5 and 7. That is exactly the observed post-stage table.
- **Observed** (#50): the raw buffer has 5, 6, 7; the post-stage table has 5 and 7.
- **Proven from source:** only the reducer can delete 6, and its predicate does.
- **Not observed:** the intermediate table between the two DELETEs. It is no longer needed to locate the defect.

Capture order is safe: the UPDATE trigger inserts every `D` (from `__pgt_old`) before every `I` (from `__pgt_new`). The paired path states *"UNION ALL preserves the required D-before-I order"* (`cdc/mod.rs`, v0.108.3 lines 2516-2591). Per row, `change_id` is therefore a valid timeline.

## 3. Every copy of the rule (#54 P0-1/2)
| Site (v0.108.3) | When it runs | Affected |
|---|---|---|
| `refresh/delta_stage.rs:164` `stage_source` | every differential refresh of an **RLS-enabled** source, **ungated** | **yes: the #50 / Fedora path** (`ax.orders` has FORCE RLS) |
| `cdc/mod.rs:1501` `compact_change_buffer` | persistent buffer compaction above a threshold, non-deferrable PK, single dependent stream | yes, when it fires. `ax.orders` has 3 dependents, so it is excluded here |
| `cdc/mod.rs:1659` `build_st_compact_sql` | per-stream-table window compaction | yes, when used |
| `cdc/mod.rs` unit test (~4349 in the snapshot) | asserts `sql.contains("rn_asc > 1 AND rn_desc > 1")` | must change together with the fix |

## 4. Truth table (#54 P0-3)
This is an executable spec: `reducer_model.py` → `reducer_model_truth_table.json` (exit 0 = proposed rule correct for every case). Each delta is what the P5 direct aggregate adds per group (+1 per staged `I` image, −1 per `D`).

| Per-row history in one window | Correct net | v0.108.3 result | Proposed |
|---|---|---|---|
| `I` | +1 new | ✓ | ✓ |
| `D` | −1 old | ✓ | ✓ |
| `I,D` | none | ✓ | ✓ |
| `D,I` (update; #50 Case B) | −old +new | ✓ | ✓ |
| **`I,D,I`** (insert then update; #50 Case A, Fedora) | +new | **✗ +old +new (ghost)** | ✓ |
| **`I,D,I`** same group (e.g. quantity change) | +1 | **✗ +2** | ✓ |
| **`D,I,D`** (update then delete) | −old | **✗ −old −mid (double decrement)** | ✓ |
| `D,I,D,I` | −old +new | ✓ | ✓ |
| **`I,D,I,D,I`** | +new | **✗** | ✓ |
| `I,D,I,D` | none | ✓ | ✓ |
| **`D,I,D,I,D`** | −old | **✗** | ✓ |
| `D,I` same group | 0 (values change) | ✓ | ✓ |

**Other dimensions:**
- **Two rows in the same group:** separate `__pgt_row_id` partitions, so they are independent.
- **Primary-key change:** `D` falls under the old identity and `I` under the new one (separate partitions); covered by the single-event rows.
- **Cross-frontier:** handled by window bounds (#50 Case B is exact).
- **Null keys:** PK columns are NOT NULL.

**Keyless sources** (`KEYLESS_ROW`, identity = content hash): identical rows share an identity, so a "history" is a multiset. Neither positional rule is valid (3 identical inserts → v0.108.3 keeps 2, proposed keeps 1). **The proposed rule is restricted to keyed (`SCAN_KEY`) sources**; keyless sources keep their current behaviour, plus a separate test specification for multiset (count) cancellation. Deferred-key sources: the compaction gate already excludes deferrable PKs. `stage_source` should apply the fix only where `resolve_pk_columns` is non-empty and the PK is not deferrable.

## 5. Why only the product rollup goes wrong, and the #49 variants (#54 P0-4)
- **Observed:** all three stream tables' stages lose `D` (#50 `40-AB-trace-*`). Only `st_day_product_status` goes wrong.
- **Source reason:** the product rollup is a plain Scan → GROUP BY, so it is P5-eligible (`aggregate.rs` `is_direct_agg_eligible` / `generate_direct_agg_delta`). It **sums staged I/D images directly**. The joined rollups go through `diff_scan_change_buffer` (`scan.rs`), which re-derives per row "earliest `D` iff existed before, latest `I` iff exists after". That re-applies the correct rule on top of the stage and hides the loss. This is source-backed; the joined-path runtime behaviour was observed as 0/0.
- **#49 1M writer drift** (16 missing / 31 extra `paid` groups, +33 orders): explained by the `I,D,I` row. A group with a wrong value counts once in each direction, and ghost `paid` groups with no source rows count only as extra.
- **#49 single 5-row repro "paid only, no cancelled": not yet explained.** The stage rule predicts `paid` +1 **and** `cancelled` +1 (#50 shape). That refresh's actual apply strategy was **`delete_insert`** (PH-D1), whereas #50's was **`merge`**.
  - **Trace to settle it (P1):** re-run that 5-row repro under the fixed `trace_refresh_fixed.sql`, with `log_merge_sql=on` and `log_delta_sql=on`. Capture the post-stage rows, the logged delete_insert apply SQL and the target rows. If the stage shows both `I` images but the target lacks `cancelled`, there is a **second, apply-side defect** in the delete_insert path.

## 6. Proposed correction (P1, needs approval)
**SQL**, in all three sites, applied only for keyed sources:
```sql
DELETE FROM <stage_or_buffer> WHERE change_id IN (
  SELECT change_id FROM (
    SELECT change_id, action,
           ROW_NUMBER() OVER (PARTITION BY __pgt_row_id ORDER BY change_id)      AS rn_asc,
           ROW_NUMBER() OVER (PARTITION BY __pgt_row_id ORDER BY change_id DESC) AS rn_desc
      FROM <stage_or_buffer> WHERE action IN ('I','D')) r
  WHERE NOT ((rn_asc = 1 AND action = 'D') OR (rn_desc = 1 AND action = 'I')))
```
**Rust shape:**
- Move the predicate into one shared builder (`crate::cdc::net_change_reduction_sql(table, keyed: bool)`) used by `stage_source`, `compact_change_buffer` and `build_st_compact_sql`, so the three copies cannot drift.
- Add a **pure** decision function (`net_change_keep(&[Action]) -> Vec<bool>`) for unit tests (AGENTS.md: separate pure logic from SPI).
- Errors stay `PgTrickleError`; no `unwrap`.

## 7. Regression plan (#54 P0-5)
| Tier | Tests | Infrastructure |
|---|---|---|
| Unit (`just test-unit`) | `net_change_keep` against the brute-force truth for every history in §4 plus a property test over random I/D sequences up to length 8 (keyed); keyless multiset spec; SQL builder emits the new predicate; **replace** the snapshot test that asserts the old predicate | none |
| Integration (`just test-integration`, Testcontainers) | Keyed source + FORCE RLS + one P5 stream table + one joined stream table. For each §4 history inside **one** window (pause, writes, manual refresh), assert symmetric `EXCEPT ALL` 0/0 on both tables. Repeat across two windows. Exercise `compact_change_buffer` (single dependent, low threshold). Keyless negative control: behaviour unchanged | Docker |
| E2E / repro | #50 fixture Cases A and B on a disposable target with the patched build; the #49 5-row repro with the trace from §5; three-table oracles; API-vs-SQL oracle; record the **actual** `merge_strategy_used` per refresh (merge and delete_insert) | disposable stack |
| Negative controls | tenant 403 / RLS-scoped reads unchanged; no FULL fallbacks introduced; freshness unchanged on 1M (refresh duration ±10 %) | disposable stack |
| Hygiene | `just fmt`, `just lint` with zero warnings | toolchain |

## 8. Prevention vs existing ghost rows, and the mitigations (#54 P0-6/7)
- **Prevention** (this fix) stops **new** drift only. Rows already persisted wrong stay wrong.
- **Detection:** run the three-table oracle on a schedule (`integration/scale/oracle_lowmem.sql` is memory-safe at 10M: 208 s at about 1 GiB) and alert on any non-zero result.
- **Repair** (separately authorised, per affected stream table): FULL refresh or reinitialise (B-2 `axapi.rebuild`), then re-run the oracle. Never automatic, never silent.

| Mitigation | Correct? | Cost (measured) | Status |
|---|---|---|---|
| FULL refresh mode for `st_day_product_status` | yes (#49 repro 5/5 correct) | **1M: 5.8 s/refresh** (vs 3.3 s DIFFERENTIAL). **10M: a full rebuild of this table took 149.8 s** under memory pressure, so it cannot keep 10M within the 30 s G2 target | approved by the human operator for the #29 demo/scale configs only; not deployed |
| Raw-source mode (#51) | bypasses stream tables | not measured; not live-verified | merged default-off; not enabled |
| **This reducer fix** | yes (model 12/12 keyed) | expected ≈ unchanged (same window query, different predicate) | **needs P1 approval** |

## 9. Approval requested (P1)
1. **Code:** implement §6 in an isolated branch (`fix/opus-54-net-change-reducer`); unit tests; `just fmt` / `just lint`. No upstream push, no merge.
2. **Build and runtime:** build a patched extension image and run §7 on a **new disposable target** (`ax-issue54-fix`, loopback port, ≤ 2 GiB, ≤ 1 CPU, ≤ 30 min, fresh volume), with a fresh preflight. Building a pgrx image is heavy on this 8 GB Mac; an alternative host may be preferable.
3. **Separately, later:** any deployment, migration, or repair of existing ghost rows.
