# G3 matched run: 10k orders, 200 OLTP TPS, 20 dashboard req/s, 5 randomised pairs

**Verdict: G3 INCOMPLETE, not a PASS.**
- **Throughput:** dashboard load did not reduce OLTP throughput at the fixed offered rate.
- **Latency:** the latency comparison is dominated by host freezes on the shared Mac and is not decisive.
- **New G2 finding:** with dashboard traffic on, the pg_trickle scheduler almost stops refreshing.

## Setup
| Item | Value |
|---|---|
| Stack | Fresh disposable Compose project `ax-g3m` (`compose.sharded.yaml`, shard A :25681, API :18192); image `sha256:94344bb9…`, PG 18.6, pg_trickle 0.108.3 |
| Data | 10k-order global seed (shard A: tenants 1, 3, 4); demo writer at 2 changes/s |
| Arms | **A** stream tables + writer · **B** A + 20 req/s real HTTP dashboard load (summary/trends/top-products/breakdown, tenants 1/3/4) · **C** same fixture, **no** stream tables (`ax_nost`) |
| Run | 5 pairs in random arm order, seed 4203; each arm `pgbench -c 4 -R 200` for 35 s, first 5 s discarded |
| Fixture parity | Before each pair, the writer is paused and C is resynced from A, with a verified count+md5 fingerprint. Per-arm base rows within a pair differ by **≤ 1.6 %**, only from writer rows added during the pair (`fixture_rows_per_arm`). |
| Host | Apple M1, 8 GB; client, API, load generator and both shards share it. The user's single-DB demo stack was paused during the run. |

## Results (raw: `arms.jsonl`, `summary.json`, `meta.json`, `../run-10k-o200-r20-matched.log`)
| Pair | Arm | Base rows | TPS (offered 200) | p95 ms | p99 ms | HTTP achieved / errors / p95 ms | Max CDC backlog | Max refresh age s | Refreshes in window | Commit→visible probes (insert, cancel) |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | A | 5,472 | 191.2 | 16.87 | 238.67 | n/a | 15,956 | 31.5 | 21 FULL | timeout, 2.76 s |
| 1 | B | 5,507 | 193.0 | 36.70 | 343.98 | 20.0 / 0 / 20.3 | 20,890 | 56.7 | **0** | timeout, 16.5 s |
| 1 | C | 5,443 | 198.8 | 8.91 | 217.91 | n/a | 0 | n/a | n/a | n/a |
| 2 | A | 5,589 | 200.5 | 6.96 | 19.92 | n/a | 15,708 | 60.0 | 21 FULL | timeout, timeout |
| 2 | B | 5,657 | **63.3** | **77,803** | 78,609 | 20.0 / 0 / 205.9 | 21,460 | **146.4** | **0** | timeout, timeout |
| 2 | C | 5,548 | 191.6 | 6.87 | 13.51 | n/a | 0 | n/a | n/a | n/a |
| 3 | A | 5,729 | 199.6 | 13.86 | 65.18 | n/a | 16,890 | 60.3 | 20 FULL | timeout, timeout |
| 3 | B | 5,778 | 198.5 | 6.90 | 23.90 | 20.0 / 0 / 9.9 | 21,222 | 69.8 | 1 FULL | timeout, timeout |
| 3 | C | 5,706 | 195.0 | 7.08 | 14.62 | n/a | 0 | n/a | n/a | n/a |
| 4 | A | 5,906 | 195.4 | 60.91 | 591.79 | n/a | 15,941 | 107.1 | 21 FULL | timeout, timeout |
| 4 | B | 5,843 | 196.8 | 31.67 | 131.59 | 20.0 / 0 / 24.9 | 21,537 | 68.8 | **0** | timeout, timeout |
| 4 | C | 5,840 | 196.1 | 7.35 | 16.54 | n/a | 0 | n/a | n/a | n/a |
| 5 | A | 5,965 | 190.6 | 6.95 | 27.51 | n/a | 16,413 | 59.9 | 22 FULL | timeout, timeout |
| 5 | B | 6,048 | 201.4 | **10,444** | 11,280 | 20.0 / 0 / 157.8 | 21,009 | 77.0 | 1 FULL | timeout, timeout |
| 5 | C | 5,959 | 195.6 | 6.60 | 8.01 | n/a | 0 | n/a | n/a | n/a |

**Quiesced exact oracle after the run** (writer paused, backlog drained): `st_day_category_status 0/0`, `st_day_product_status 0/0`, `st_hour_category_status 0/0`.
**FULL fallbacks in A+B arms:** 107. Every A-arm refresh was FULL (`COST_MODEL_PREFERRED_FULL`); none was DIFFERENTIAL.

## Scored against the PRD
| Metric | Median across pairs | Range | Reading |
|---|---|---|---|
| **G3** OLTP throughput, B vs A | **+0.7 %** | −68.4 … +5.7 % | At a fixed offered rate, the dashboard did not reduce throughput. The −68 % is the pair-2 host freeze. |
| **G3** OLTP p95, B vs A | +117.5 % | −50 … +1.1 M % | **Not decisive.** Two of five B arms contain multi-second host freezes. Excluding them gives three pairs at +117, −50 and −48 %. The PRD threshold (< 25 % Good / < 10 % Great) is **not demonstrated either way**. |
| Maintenance cost, A vs C (separate from G3) | TPS −0.4 %, p95 +89 % | p95 +1 … +729 % | CDC triggers plus FULL refreshes add tail latency. |
| **G2** freshness under write load | **FAIL** | n/a | Refresh age reached 31–146 s. 18 of 20 commit→visible probes in A/B timed out (> 30 s); the 2 that completed took 2.8 s and 16.5 s. |

## Anomalies (kept in the data, not removed)
- **Pair 2 B: host freeze.** The 35 s arm took **92.6 s** of wall time, with 0 lock waits, 0 failed transactions, 0 HTTP errors and 0 refreshes. `pgbench -R` measures from each transaction's scheduled start, so a ~60 s whole-host stall becomes a 67 s p50. This is consistent with the Mac's memory pressure (swap near full).
- **Pair 5 B:** the same signature on a smaller scale (p95 10.4 s, HTTP p95 158 ms).
- **Scheduler starves under dashboard load (new).** A arms record 20–22 refreshes per window; **B arms record 0–1**, with a larger backlog (≈ 21k vs ≈ 16k) and older data. This matches the #42 P0-2 live-write stall: while the API is serving traffic, shard dispatch stops. **Root cause not isolated** (see `docs/demo-evidence/ax-demo42/stall/`). Upstream engine work needs human approval.

## Limits
- One shared 8 GB laptop.
- 10k representative orders, not organiser data or the 1M/10M scale.
- A 35 s arm per run.
- One offered rate (200 TPS) and one dashboard rate (20 req/s).
