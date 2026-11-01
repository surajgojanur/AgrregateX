# Independent 10M Scale Evidence Audit

Source: PR [#57](https://github.com/surajgojanur/AgrregateX/pull/57), commit `b0f360685c33f67516c6ef0c1c6170b1575d14ee`.
Audit method: standard-library parsing and independent arithmetic on checked-in artifact JSON/text; no database or API calls.

## Artifact facts independently cross-checked

- 10M dataset snapshot reports 10000000 rows, 100 tenants, PostgreSQL PostgreSQL 18.6 (Debian 18.6-1.pgdg12+2) on aarch64-unknown-linux-gnu, compiled by gcc (Debian 12.2.0-14+deb12u1) 12.2.0, 64-bit, pg_trickle 0.108.3, generator seed 42.
- Scenario artifacts enumerate 72 10M cases and 3600 requests; stored errors total 0.
- Recomputed G1 counts from per-case p95 fields: 71/72 below 200 ms and 72/72 below 1,000 ms. Worst recorded p95: 240.56 ms, ('top_products', 'largest', '90d').
- Matched G5 ratios: 72 scenarios; median 1.18x; 66 below 2x; 71 below 5x; worst 5.18x.
- Initial-load oracle output contains three stream tables with 0 missing / 0 extra rows: True.
- API/source count artifact reports 100 tenant matches, totals 10000000 vs 10000000.

Evidence paths in the source PR: `hackathon/integration/scale/results/10m-100t-http/{summary.json,scenarios.json,growth_vs_1m.json}`; `10m-100t-proof/{db-snapshot.json,api-vs-db-100-tenants.json,oracle-lowmem.txt}`; plus `1m-10t-http/{summary.json,scenarios.json}`.

## Evidence limits and qualification

- Representative synthetic data (seed 42), not organizer data.
- 50 stored requests per scenario; acceptance protocol requires at least 200 successful HTTP samples per scenario.
- Only aggregate p50/p95/p99/max/mean are stored; raw per-request timing samples are absent, so nearest-rank percentiles cannot be independently recomputed.
- The 72-case six-window matrix does not itself establish the protocol's complete, exact acceptance matrix unless each named requirement is mapped and approved.
- Stored JSON, host logs, counts, and hashes do not independently authenticate database execution or immutable image provenance.
- G2 sustained commit-to-visible at 10M: NOT TESTED; G3 write safety at 10M: NOT TESTED.
- G4 post-mutation correctness at 10M: NOT TESTED; initial-load oracle does not test incremental updates/cancellations.
- G5 is representative synthetic growth evidence, not qualified official acceptance. Tenant matching is by size rank, not same tenant IDs; the largest tenant grew about 5.7x.

## Reported run incidents and setup

- The source report says the init server exceeded its 60-second `pg_ctl` shutdown wait while checkpointing about 4 GB of WAL; the container exited, then recovered by crash replay on restart. The report says no committed data was lost.
- The original all-in-one hashed oracle with `work_mem=128MB` was OOM-killed in a 2 GiB container. A memory-bounded `oracle_lowmem.sql` was used for the later three-table result.
- Both HTTP reports describe auth disabled for the load client, serial requests after warmup, and no concurrent writers. These measurements do not establish authenticated multi-tenant load behavior.
- The report supplies an abbreviated image digest and no complete matched Git/config/dataset fingerprint across both scale arms; strict G5 provenance remains insufficient.

## Status categories

| Check | Audit classification |
|---|---|
| 1m_scenario_artifact_consistency | VALIDATED FROM ARTIFACT |
| 10m_scenario_artifact_consistency | VALIDATED FROM ARTIFACT |
| 10m_dataset_snapshot_consistency | VALIDATED FROM ARTIFACT |
| dataset_execution_authenticity | REPORTED BUT NOT INDEPENDENTLY RECOMPUTABLE |
| matched_run_provenance | INSUFFICIENT EVIDENCE |
| g1_threshold_arithmetic | VALIDATED FROM ARTIFACT |
| g1_percentile_source | REPORTED BUT NOT INDEPENDENTLY RECOMPUTABLE |
| g1_official_qualification | INSUFFICIENT EVIDENCE |
| g2_10m_freshness | NOT TESTED |
| g3_10m_write_safety | NOT TESTED |
| g4_10m_post_mutation | NOT TESTED |
| g5_official_qualification | INSUFFICIENT EVIDENCE |
| growth_arithmetic | VALIDATED FROM ARTIFACT |
| growth_percentile_recomputation | REPORTED BUT NOT INDEPENDENTLY RECOMPUTABLE |
| initial_load_oracle_values | VALIDATED FROM ARTIFACT |
| oracle_execution_authenticity | REPORTED BUT NOT INDEPENDENTLY RECOMPUTABLE |

## Judge-safe wording

On representative synthetic data, the recorded 10M/100 run completed 3,600 serial HTTP requests across 72 scenarios with 50 samples each and no recorded errors; 71 stored p95 values were below 200 ms and all 72 below 1 s. Stored 10M/1M p95 ratios had median 1.18x, 66 below 2x and 71 below 5x. This is not organizer-data qualification, does not include raw timing samples, and does not establish post-mutation G4 correctness.

Do not claim:

- Official G1/G5 acceptance passed
- All scenarios meet the Great threshold
- 10M incremental correctness passed after writes/cancellations
- G2 or G3 passed at 10M
- 10M organizer-data compatibility

## Next experiment

Repeat the same 1M/10M scenario matrix with at least 200 successful raw HTTP timings per scenario and preserved sample-level latency records; hold host, image digest, code revision, query windows, warmup, and workload constant. Then run separate 10M sustained-write freshness and post-mutation three-table correctness checks after the #54 reducer is validated. Organizer data and approval remain required for official acceptance.
