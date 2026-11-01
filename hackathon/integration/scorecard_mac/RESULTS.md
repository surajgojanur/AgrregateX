# Results: phase R0 (read-only), 2026-11-01

Every number here was either recomputed from committed raw artifacts or produced by a test re-run on `04f03b9`. **No live measurement was made.** The raw output files are in `evidence/`.

## Offline test re-runs (this commit, Mac)
| Suite | Command (cwd) | Result |
|---|---|---|
| API unit tests | `python -m unittest discover -s tests -p 'test_*.py'` (`hackathon/app`) | **55/55 OK** |
| Benchmark acceptance + HTTP baseline (Codex-owned, run read-only) | `python -m unittest test_acceptance test_http_baseline` (`hackathon/benchmark`) | **25/25 OK** |
| Benchmark G4 protocol | `python -m unittest hackathon.benchmark.test_g4_protocol` (repo root) | **16/16 OK** |
| Evidence verifier tests | `python -m unittest test_verify_scale_evidence` (`benchmark/evidence_review`) | **15/15 OK** |
| Evidence verifier on `integration/scale/results` | `verify_scale_evidence.py` | artifact arithmetic **VALIDATED**; official qualification **INSUFFICIENT EVIDENCE**; post-mutation correctness **NOT TESTED** |
| G4 reducer truth table | `python3 -I integration/g4_fix/reducer_model.py` | exit 0 (old rule 5/12 wrong, new rule 12/12) |
| Frontend | `npm run lint`, `npm test`, `npm run build` | lint OK; **24/24**; build OK |
| pg_trickle crate with the PR #58 fix (earlier today, branch `fix/opus-54-net-change-reducer`) | `scripts/run_unit_tests.sh pg18` + fmt + clippy + lint scripts | 2,682 unit tests pass. Cited, not re-run here |

## G1 / G5 recomputation (`evidence/recompute-g1-g5.txt`)
- **1M:** 3,600 requests, 0 errors, 0 non-200; p95 < 200 ms in 72/72 scenarios; worst p95 60.77 ms, worst p99 / max 173.52 ms.
- **10M:** 3,600 requests, 0 errors, 0 non-200; p95 < 200 ms in **71/72** and < 1 s in **72/72**; the one over 200 ms is `top_products`, largest tenant (t1, 1,930,247 orders), 90 d: p50 68.97 / p95 240.56 / p99 457.32 ms.
- **G5:** 72/72 keys matched; median **1.18×**, min 0.41×, max **5.18×**, < 2× in 66, < 5× in 71. This equals the stored `growth_vs_1m.json` exactly. Top ratios:

| Ratio | Scenario | p95 1M → 10M (ms) | Role tenant orders 1M → 10M |
|---|---|---|---|
| 5.18× | top_products, largest, 90 d | 46.43 → 240.56 | 340,560 → 1,930,247 |
| 3.62× | breakdown, largest, partial 7 d | 10.12 → 36.65 | same |
| 3.37× | summary, largest, partial 7 d | 11.39 → 38.35 | same |
| 2.27× | top_products, largest, partial 7 d | 15.49 → 35.14 | same |
| 2.12× | trends, largest, 90 d | 7.34 → 15.54 | same |
| 2.07× | top_products, median, 30 d | 12.28 → 25.40 | 56,965 → **37,901** |

## G2 recomputation (`evidence/recompute-g2.txt`)
- 8 probes, 0 timeouts; lags of 10.7, 12.0, 13.9, 15.2, 18.7, 20.0, 20.9 and 24.0 s.
- **Median 16.96 s** (the published "18.7 s" is the upper median); max 24.0 s.
- Mutation kinds: insert and cancel only.

## G3 / G4 (reviewed, not recomputed)
- **G3:** `integration/g3/results/10k-o200-r20-matched/REPORT.md` reports "G3 INCOMPLETE, not a PASS". The B-vs-A p95 median is +117.5 % with host freezes in 2/5 B arms. This audit agrees: NOT QUALIFIED.
- **G4:** `1m-10t-http-writer5/oracle-quiesced-drained.txt` shows `st_day_product_status 16/31`, while the category and hour rollups are 0/0. `drift-analysis.txt` shows the extras are 31 paid groups and the missing ones 16 paid groups on 2026-10-31, with stream minus source = +33 paid, and 164 seed orders were updated by the writer. **FAIL** stands.

## Not run (needs approval: RUNBOOK P1–P6)
- G4 patched-runtime regression.
- B4 live.
- G2 exact-value probes.
- G1 at ≥ 200 samples, with concurrency.
- G3 on a resourced host.
- FR2 edge cases.
- Live re-verification of FR5 and B1–B3 on this commit.
