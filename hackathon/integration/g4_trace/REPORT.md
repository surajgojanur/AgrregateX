# #50 runtime trace of the G4 "ghost paid" defect: verdict

**Verdict: STAGING DEFECT CONFIRMED** (raw negative image present in the CDC buffer, then lost during staging).
- **Boundary not isolated:** whether the loss happens in the reducer or in the visibility filter is **inferred, not observed**. Stock diagnostics expose no pre-reducer / post-reducer boundary (see §4).
- **Engine:** PostgreSQL 18.6 + pg_trickle **0.108.3**, image index `sha256:94344bb9…` (arm64 child).
- **Scope of changes:** no Rust patch, no instrumentation build, no FULL switch, no repair of any existing database.

## 1. Target, approval and deviations
| Item | Value |
|---|---|
| Approval | Human operator @shridhar618 relaxed the host RAM/swap gate for the Mac only; recorded on #50 *before* launch (comment 6550209096). The Mac preflight failed as specified (1.25 GiB available, active swapping): `preflight-mac.txt` |
| Target | Project `ax-issue31-g4-repro`, container `ax-issue31-g4-repro-db`, fresh volume `ax-issue31-g4-repro_data`, DB `ax_g4_repro`, loopback 25634, 1 GiB, 1 CPU, `pg_trickle.enabled=off`, `mac-arm64-override.yaml` (platform only). The user's demo stack was paused with `stop` and restarted afterwards |
| Runtime | `PostgreSQL 18.6 (Debian 18.6-1.pgdg12+2) on aarch64`, `pg_trickle.enabled=off`, defaults `aggregate_fast_path=on`, `merge_strategy=auto`, `threshold=0.01` (primary_default: no SET) |
| Wall clock | Target start 22:52:27Z, last capture 22:54:06Z (**~1.7 min**), stopped 22:54:48Z, volume **retained** |
| Data | 80 baseline orders plus orders 1001 (Case A) and 1002 (Case B) = 82 |
| **Deviation 1** | Prepared `fixture.sql` aborted at line 40: `20_security.sql` RLS changes **suspend** all three stream tables (`SOURCE_DEPENDENCY_AMBIGUOUS`), and the fixture then refreshes a suspended table. Bootstrap was completed with production `init.sh`'s own step (`reinitialize_stream_table` × 3), then the fixture's remaining manual refreshes, before any case data (`02b-fixture-completion.txt`). Baseline oracle 0/0/0; scheduler idle (history 6 → 6 over 5 s) |
| **Deviation 2** | Prepared `trace_refresh.sql` line 75 interpolates psql booleans unquoted (`'stage_observed',t` gives `column "t" does not exist`). With `ON_ERROR_STOP`, **every trace's transaction, including its refresh, rolled back** (files `13-*`, `21-*`: evidence captured, nothing applied). Re-run with `trace_refresh_fixed.sql`, which quotes only that line (diff in `controller.log`). |
| Consequence | Because of deviation 2, Case B's update and all three Case A events were consumed by **one** refresh window. They touch disjoint groups (B: product 2 / 2026-11-21; A: product 1 / 2026-11-20). Case B's *setup* (paid materialised, oracle 0/0) was a separate, committed earlier window |

## 2. OBSERVED (`40-AB-trace-st_day_product_status.txt`)
**Exact window** for source 17462 (`ax.orders`): frontier `0/22663E0` → `0/22EC798`. The logged resolved delta SQL uses `WHERE c.lsn > '0/22663E0' AND c.lsn <= '0/22EC798'`.

| change_id | LSN | xid | Order | Raw buffer before refresh | Post-stage `pg_temp.__pgt_cdc_1_17462` |
|---|---|---|---|---|---|
| 2 | 0/22663E0 | 943 | 1002 | I paid (consumed by the setup window; outside this window) | n/a |
| 3 | 0/22A85A8 | 948 | 1002 (B) | **D paid** | **D paid** ✓ |
| 4 | 0/22A85A8 | 948 | 1002 (B) | I cancelled | I cancelled ✓ |
| 5 | 0/22EC560 | 953 | **1001 (A)** | I paid | I paid |
| 6 | 0/22EC798 | 954 | **1001 (A)** | **D paid** | **— absent —** |
| 7 | 0/22EC798 | 954 | **1001 (A)** | I cancelled | I cancelled |

- **Actual refresh** (`pgt_refresh_history` refresh_id 16): `DIFFERENTIAL`, `COMPLETED`, `MANUAL`, `delta_row_count 4`, **`merge_strategy_used = merge`**, `was_full_fallback = f`. `PGS_PROFILE … mode=INCR strategy=merge`. Log `MT-8 fallback=partition_or_trigger_apply_constraint`: the **vector aggregate path was not used**. The SQL aggregate delta (`__pgt_cte_agg_delta_1`, I/D sums over the stage table) feeds the MERGE.
- **Target after commit:** product 1 / 2026-11-20 holds **both `paid` = 1 and `cancelled` = 1**; source holds only `cancelled` (order 1001). Product 2 / 2026-11-21 holds only `cancelled` = 1, which is correct.
- **Oracle after all three refreshes** (`41-AB-oracle-final.txt`, one REPEATABLE READ snapshot): `st_day_product_status` **0 missing / 1 extra**; `st_day_category_status` 0/0; `st_hour_category_status` 0/0. This is **the same shape as Fedora** (one extra `paid` group, joined tables exact).
- **Joined tables** (`40-AB-trace-st_day_category_status.txt`, `…hour…`): their post-stage tables (`__pgt_cdc_2_17462`, `__pgt_cdc_3_17462`) **also lack change 6**, holding only I paid (5) and I cancelled (7) for order 1001. Their refreshes (ids 17, 18: DIFFERENTIAL, `merge`, no fallback) nevertheless produced exact results.
- **Case B (paid materialised before the window):** staging kept `D(paid)` + `I(cancelled)`; the group is correct.

## 3. INFERRED (not directly observed)
- **Where the D is lost.** The loss occurs inside staging (`DeltaStage::stage_source`), between the raw buffer copy and the post-stage relation. Changes 6 and 7 share LSN and xid 954, so a visibility/xid filter would not drop the D while keeping the I of the same transaction. The **reducer/compaction step is the likely locus**, matching the #48 source audit's prediction for `I(paid), D(paid), I(cancelled)` (discard the negative image, keep both positive images). Not separately observed: see §4.
- **Why only the single-table aggregate is wrong.** All three stages lose change 6. The product rollup's delta is a direct signed sum of stage images (I paid +1, I cancelled +1), which yields the ghost. The joined rollups' producers evidently do not depend on the lost D; they probably re-derive from current joined source state. That mechanism is inferred from outcomes only.
- **Mac PR #49 "paid only" manifestation.** In that run, 5 rows were inserted in one statement and updated in one statement at 1M, and `cancelled` never appeared. This differs from this run and from Fedora (paid + cancelled). It was **not reproduced here**; it may be a different staging outcome of the same reducer (for example a dropped final I) under multi-row statements. No shared cause is assumed.

## 4. Not observed / INCONCLUSIVE
- **Pre-reducer vs post-reducer vs post-visibility rows:** stock tooling exposes only the raw buffer copy and the final `__pgt_cdc_*`. Localising reducer vs visibility needs **minimal instrumentation, separately approved**.
- **Materialised aggregate delta:** `pg_temp.__pgt_delta_1` does not exist for the `merge` path. The delta rows were not observed (SQL text only), so "producer computed exactly +1 paid" is inferred from stage plus target.
- **Comparison runs** (`comparison_fast_off_merge`, `comparison_fast_off_auto`): not run. Each needs a fresh fixture.
- **API impact:** not exercised (no API in the target). Expected effect: tenant 1 summary, Top-N and status breakdown over 2026-11-20 would over-count `paid` by 1 order / 1 unit / 1,000 cents.

## 5. Recommendation (proposals only; each needs separate approval)
1. **Fix (upstream, Rust, needs approval):** correct the staging reducer so per-row history keeps the **earliest D iff the history starts with D** (row existed before the window) and the **latest I iff it ends with I**, discarding intermediate images. For `I,D,I` keep only the last I; for `D,I` keep both. Validate with this exact A/B pair, multi-row-statement variants (to explain #49), keyed/RLS cases and three-table oracles before any patch PR.
2. **Interim mitigation (config, needs approval):** `refresh_mode => 'FULL'` for `ax.st_day_product_status` only. Measured in #49 at 1M: correct, 5.8 s per refresh vs 3.3 s.
3. **Detection:** run the three-table oracle on a schedule and alert on any non-zero result. Existing drift is repaired by FULL refresh or reinitialisation (B-2 rebuild).
4. **Fix the two prepared-script defects** (deviations 1 and 2) in #48's protocol, owned by Codex.

## Files
- **Logs:** `controller.log` (timeline), `controller.sh`, `mac-arm64-override.yaml`, `trace_refresh_fixed.sql`.
- **Numbered captures:** `00-…41-*` (raw outputs, including the rolled-back traces).
- **Server log:** `30-server-log-filtered.txt`.
- **Secrets:** none. The superuser password was a throwaway generated inside the controller, never printed and unset after start.
