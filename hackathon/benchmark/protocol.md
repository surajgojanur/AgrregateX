# P2 acceptance protocol (P3 contract v2)

Only disposable databases explicitly provisioned for benchmarks may receive mutations.
No default DSN, production volume access, automatic loading, or 10M execution.
The current artifact is a scaffold, not completed FR1–FR7 qualification.

## Functional matrix

FR1: compare counts, units and integer-cent sales with raw orders. Counts include
all statuses; sales/units exclude cancelled/refunded. Check empty intervals.
FR2: compare UTC hour/day buckets, including explicit zero buckets.
FR3: aggregate all products over the requested interval before LIMIT 10; test 11
products, tied revenue, units tie, deterministic product-ID tie and winners that
change across days. Never merge daily Top-N lists.
FR4: compare category/status totals including product category corrections.
FR5: test every signed-cookie identity/path pair across 100 identities, missing/invalid tokens,
forged body/query/header tenant, hidden foreign IDs and connection reuse after
switching tenant. Verify non-owner role, no BYPASSRLS, source AND stream RLS.
FR6: insert, amount/quantity correction, product move, historical timestamp move,
cancellation, refund, delete, rollback, concurrent/replayed events. After every
commit poll exact expected values, then compare all three stream tables using
symmetric EXCEPT ALL in a consistent snapshot after quiescence.
FR7: real HTTP requests and documented error/status/response schema, not SQL-only
latency. API contract is available in opus-sharding.md §5; live cases remain NOT TESTED.

Time cases: [from,to), exact midnight/hour, one microsecond either side, offset
normalization, empty range, reversed range, partial-hour edges, leap day and DST.
Compare source and API independently, never use API SQL as its own oracle.

## Paired safety experiment

Use the SAME engine, fixture snapshot, clients, rate and duration in both arms.
Keep maintenance enabled in BOTH arms. Baseline has no dashboard requests; treatment
adds real HTTP traffic. Randomize AB/BA with fixed seed across at least five pairs.
Warm both arms identically; reset fixtures and drain between arms. Record actual
completed operations, elapsed time, TPS, transaction/commit p50/p95/p99, errors,
timeouts, dashboard success and latency, CPU/RAM/IO/lock waits. Include a separate
no-stream-table arm to quantify maintenance cost. Never equate these comparisons.
Strict gates: transaction p95 ratio <1.1 AND throughput ratio >.9 per pair.
Record offered and achieved request rates; overload/errors cannot count as PASS.

## Sustained freshness

Run bounded fixed-rate background writes while inserting uniquely identifiable
probe orders. Timestamp with monotonic clock immediately after COMMIT returns.
Poll from a separate autocommit connection until exact count/cents/status expected
for the dedicated probe key appear; then check changes, cancellations and deletes.
A timeout is a failed sample, never discarded. Keep raw commit/visible timestamps,
writer rate/TPS/errors and every refresh record. Timestamp metadata alone is not
proof of visibility. Compare source/rollups after writers stop.

## Scale experiments

100k first: 10 skewed tenants, bounded writers, timeouts and resource sampling.
1M: separately authorized safe resource preflight, 10 populated skewed tenants;
repeat exactly the same queries, windows, key cardinality and concurrency.
10M PLAN ONLY: 100 populated skewed tenants, explicit human approval, disk/RAM gate,
separate disposable dataset. No command in this harness launches this workload.
For G5 compare matched query cases at 1M and 10M with identical hardware/config,
warmup, engine image and measurement method; report every ratio, not just averages.

Require actual refresh history action DIFFERENTIAL, completed refreshes >0, zero
FULL fallbacks, no failed refresh, bounded backlog; configured mode is insufficient.
Capture git SHA, image digest, extension/server version, hardware, dataset seed,
row counts, tenant skew and complete raw output with every report.

## CI investigation

Existing build.yml uses ubuntu-latest, matrix builds with 20-minute timeout, and
10/5/15 minute auxiliary jobs. That is configuration, not demonstrated available
RAM/disk or a successful 0.108.4 A/B build. Dockerfile.demo uses mutable rust:latest,
nightly and unpinned cargo-pgrx install, while Cargo.toml pins pgrx 0.18.0; a controlled
build must pin toolchain, cargo-pgrx and base digest for both arms. Candidate must
also have a correctness-proven patch (row-ID-only join is not approved).
Before any dispatch obtain approval and runner budget/quota; preflight free RAM,
disk, CPUs and caches, cap parallelism, run control/candidate sequentially, retain
image digests and build logs. No workflow or expensive build was launched.

## Evidence

Python offline tests validate report boundaries, malformed inputs and fail-closed
missing evidence. No live SQL/HTTP, mutation, throughput, freshness or scale PASS
is claimed. Existing databases remain untouched. just fmt/lint require absent just
and Rust tooling; report that blocker instead of claiming success.

## Evidence validator v2 (Issue31)

CLI already existed and is retained: `python hackathon/benchmark/acceptance.py evidence.json > report.json`.
Exit1 for unqualified evidence is intentional. No duplicate entry point or output flag.

Legacy flat timings, booleans and oracle arrays cannot establish VERIFIED coverage. `functional` maps
FR ids to exact case records listed in acceptance.CASES; each carries case, source=live, execution=real_sql_http,
comparison=independent_sql_or_security_assertion, nonempty expected object, equal actual object, run_id and artifact.
Runs must have live artifacts and execution=measured. `artifacts` maps ids to relative paths and SHA256;
resolved files must stay within the evidence directory, be nonempty and <=64MiB. Fixture artifacts used
in tests validate parsing only, and must never be submitted as experimental evidence.

G1 requires all 48 endpoint/tenant-size/window scenarios in SCENARIOS, >=200 successful full HTTP timings
each, zero errors/timeouts and matched measured 10M/100 organizer runs. G2 requires insert/update/cancel/
historical/delete, >=20 exact commit-to-visible samples per mutation under sustained writes, same scale.
G3 requires >=5 unique matched pairs, 10M/100, no errors/timeouts; reports latency slowdown and throughput
regression separately. Both strict <10% gates apply. G4 requires every configured shard, exactly three named
stream tables, integer missing/extra zero counts, quiescence and real run artifacts. G5 requires all 48 cases,
raw >=200 HTTP samples at measured 1M/10 and 10M/100 organizer runs, same hardware/image/Git/workload/
config fingerprint, and recomputes nearest-rank p95 ratios (<2x). Run fields: orders, populated_tenants,
dataset_kind=organizer, execution=measured, hardware, image_digest, git_sha, workload, config_sha256, dataset_sha256.
Case collections: latency_cases (scenario,http_ms), freshness_cases (mutation,seconds,method=commit_to_visible_exact_values,
sustained_writes=true), oracle_runs (shard,quiesced,tables), growth_pairs (scenario,run_1m,run_10m,samples_1m,
samples_10m,measurement=http_p95_nearest_rank). All records need source=live, artifact and run_id where applicable.

Offline JSON can be forged, including references to fabricated files. Hashes verify consistency, not truth.
The tool now exposes automated_candidate_pass but NEVER grants official_pass. Independent organizer dataset
and execution/provenance review is a separate mandatory gate. This deliberately preserves exit1 until such
a trusted certification mechanism exists. Representative or mock evidence cannot qualify.

G3 safety records additionally require latency_statistic=transaction_p95, at least 200 completed
transactions per arm (baseline_transactions/dashboard_transactions), and duration_s>=20. No pair
passes merely because the provided throughput number is fast. Minimum counts are coverage floors,
not a statistical confidence claim.

Issue31 execution evidence: acceptance tests16/16, sharding tests18/18, reference library fixture
tests11/11 and reference demo fixture tests7/7 PASS. bash syntax/diff checks PASS. These are synthetic
harness validations only, not live FR or G qualification. just fmt/lint unavailable because just is absent.
Fedora available RAM1.4GiB/swap used5.1GiB => no new disposable stack. No 10k/100k/1M/10M or live
fault run performed. Existing database, localhost8093 and unrelated services were untouched.
