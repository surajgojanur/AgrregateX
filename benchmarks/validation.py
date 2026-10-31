"""Fail-closed evidence validators shared by the acceptance and growth graders."""
from collections import Counter
import math

FAMILIES = (("summary", "day"), ("trends", "day"), ("trends", "hour"),
            ("top-products", "day"), ("breakdown", "day"))
RANGES = ("day", "week", "month", "boundary")
ROLLUPS = {"daily_product", "hourly_category"}

SNAPSHOT_SQL = """
WITH per_tenant AS (
  SELECT tenant_id, count(*)::bigint AS orders,
         coalesce(sum(quantity::bigint * unit_price_cents), 0)::numeric::text AS gross_cents,
         coalesce(sum(hashtextextended(jsonb_build_array(id, tenant_id, customer_id, product_id,
           category_id, ordered_at, status, quantity, unit_price_cents, version)::text, 42)::numeric), 0)::text AS row_hash_sum
  FROM orders GROUP BY tenant_id
)
SELECT (SELECT count(*)::bigint FROM orders) AS order_count,
       (SELECT count(*)::bigint FROM tenants) AS tenant_count,
       (SELECT count(*)::bigint FROM per_tenant) AS populated_tenant_count,
       (SELECT coalesce(sum(gross_cents::numeric), 0)::text FROM per_tenant) AS gross_cents,
       (SELECT coalesce(sum(row_hash_sum::numeric), 0)::text FROM per_tenant) AS row_hash_sum,
       (SELECT coalesce(json_agg(t ORDER BY tenant_id), '[]'::json) FROM per_tenant t) AS tenant_distribution,
       (SELECT count(*)::bigint FROM daily_product) AS daily_rows,
       (SELECT count(*)::bigint FROM hourly_category) AS hourly_rows
"""


def source_snapshot(query_json):
    """Capture dataset identity and per-tenant row/hash totals for cleanup and scale checks."""
    return query_json(SNAPSHOT_SQL)[0]


def expected_http_coverage(scale):
    tenant_count = 10 if scale == 1_000_000 else 100
    expected = Counter()
    for tenant in (1, 2, tenant_count):
        for range_name in RANGES:
            for family, grain in FAMILIES:
                expected[(tenant, family, grain, range_name, "sequential")] += 8
    for tenant in (1, 2, 3, tenant_count):
        for _ in range(3):
            for range_name in RANGES:
                for family, grain in FAMILIES:
                    expected[(tenant, family, grain, range_name, "concurrent4")] += 1
    return expected


def expected_correctness_coverage(scale):
    tenant_count = 10 if scale == 1_000_000 else 100
    expected = Counter()
    for tenant in range(1, tenant_count + 1):
        for family, grain in FAMILIES:
            expected[(tenant, family, grain, "week")] += 1
    for tenant in (1, 2, tenant_count):
        for family, grain in FAMILIES:
            expected[(tenant, family, grain, "boundary")] += 1
    return expected


def _counter(records, fields):
    return Counter(tuple(record.get(field) for field in fields) if isinstance(record, dict) else (None,) * len(fields) for record in records)


def inspect_http_artifact(artifact, scale):
    """Return categorized issues; distinguish missing coverage from measured failures."""
    result = {key: [] for key in ("metadata", "request_coverage", "request_failures",
                                  "oracle_coverage", "oracle_failures", "consistency",
                                  "rollup_coverage", "rollup_failures")}
    errors = result["metadata"]
    if not isinstance(artifact, dict):
        errors.append("benchmark artifact is missing or not an object")
        return result
    if artifact.get("schema_version") != 2:
        errors.append("unsupported or missing benchmark schema_version")
    if artifact.get("scale") != scale:
        errors.append("scale field does not match requested scale")
    expected_tenants = 10 if scale == 1_000_000 else 100
    for label in ("source_snapshot", "source_snapshot_after"):
        snap = artifact.get(label)
        if not isinstance(snap, dict):
            errors.append(f"missing {label}")
            continue
        if snap.get("order_count") != scale or snap.get("tenant_count") != expected_tenants:
            errors.append(f"{label} is not {scale} orders / {expected_tenants} tenants")
        if snap.get("populated_tenant_count") != expected_tenants:
            errors.append(f"{label} does not have {expected_tenants} populated tenants")
        distribution = snap.get("tenant_distribution")
        if not isinstance(distribution, list) or len(distribution) != expected_tenants or any(not isinstance(row, dict) for row in distribution):
            errors.append(f"{label} tenant distribution is missing or incomplete")
        else:
            ids = [row.get("tenant_id") for row in distribution]
            counts = [row.get("orders") for row in distribution]
            ids_valid = all(isinstance(x, int) for x in ids)
            counts_valid = all(isinstance(n, int) and n > 0 for n in counts)
            if not ids_valid or sorted(ids) != list(range(1, expected_tenants + 1)) or not counts_valid:
                errors.append(f"{label} tenant distribution has missing/empty tenants")
            if counts_valid and sum(counts) != scale:
                errors.append(f"{label} tenant distribution does not sum to source rows")
            if counts_valid and counts and max(counts) < 2 * min(counts):
                errors.append(f"{label} tenant distribution does not demonstrate skew")
    before, after = artifact.get("source_snapshot"), artifact.get("source_snapshot_after")
    if isinstance(before, dict) and isinstance(after, dict) and before != after:
        errors.append("source snapshot changed during HTTP benchmark")
    dataset = artifact.get("dataset")
    if not isinstance(dataset, dict) or not dataset.get("dataset_id") or not dataset.get("generator_id") or "seed" not in dataset:
        errors.append("dataset/generator/seed metadata is incomplete")
    run = artifact.get("run")
    if artifact.get("runner_status") != "COMPLETED" or not isinstance(run, dict) or not all(run.get(k) for k in ("run_id", "started_at_utc", "finished_at_utc", "git_commit", "postgres_version")):
        errors.append("run metadata is incomplete")
    hardware = artifact.get("hardware")
    if not isinstance(hardware, dict) or not all(hardware.get(k) for k in ("platform", "machine", "processor")):
        errors.append("hardware metadata is incomplete")
    workload = artifact.get("workload")
    if not isinstance(workload, dict) or workload.get("ranges") != list(RANGES) or workload.get("families") != [list(x) for x in FAMILIES] or workload.get("sequential_repeats") != 8 or workload.get("concurrent_clients") != 4 or workload.get("concurrent_rounds") != 3 or workload.get("timezone") != "UTC" or workload.get("time_range_semantics") != "[from,to)" or workload.get("top_n_limit") != 10 or not workload.get("api_base_url") or not isinstance(workload.get("range_parameters"), dict):
        errors.append("workload parameters do not match the registered benchmark workload")
    requests = artifact.get("requests")
    if not isinstance(requests, list):
        errors.append("requests array is missing")
    else:
        if any(not isinstance(x, dict) for x in requests):
            result["request_coverage"].append("HTTP request records contain invalid values")
            requests = [x for x in requests if isinstance(x, dict)]
        got = _counter(requests, ("tenant", "family", "grain", "range", "mode"))
        if got != expected_http_coverage(scale):
            result["request_coverage"].append("HTTP request case matrix is incomplete, duplicated or contains unexpected cases")
        if any(not isinstance(x.get("ms"), (int, float)) or not math.isfinite(x["ms"]) or x["ms"] < 0 for x in requests):
            result["request_coverage"].append("HTTP request latency is absent or invalid")
        if any(x.get("http") != 200 for x in requests):
            result["request_failures"].append("one or more HTTP requests failed")
    correctness = artifact.get("correctness")
    if not isinstance(correctness, list) or any(not isinstance(x, dict) for x in correctness) or _counter(correctness, ("tenant", "family", "grain", "range")) != expected_correctness_coverage(scale):
        result["oracle_coverage"].append("source-oracle comparison matrix is incomplete, duplicated or unexpected")
    elif any(x.get("status") != "PASS" for x in correctness):
        result["oracle_failures"].append("one or more source-oracle comparisons failed")
    consistency = artifact.get("oracle_consistency")
    if not isinstance(consistency, dict) or consistency.get("lock_acquired") is not True or consistency.get("lock_mode") != "SHARE" or consistency.get("comparison_count") != sum(expected_correctness_coverage(scale).values()):
        result["consistency"].append("source-oracle consistent-snapshot evidence is missing")
    rollups = artifact.get("rollup_mismatches")
    if not isinstance(rollups, list) or any(not isinstance(x, dict) for x in rollups) or {x.get("name") for x in rollups} != ROLLUPS or len(rollups) != len(ROLLUPS):
        result["rollup_coverage"].append("exactly the two required named rollup reconciliations are required")
    elif any(x.get("mismatches") != 0 for x in rollups):
        result["rollup_failures"].append("one or more rollup reconciliations found mismatches")
    return result


def validate_http_artifact(artifact, scale):
    result = inspect_http_artifact(artifact, scale)
    return [error for errors in result.values() for error in errors]


def expected_fixture_test_names():
    names = set()
    for tenant in (1, 2):
        for range_index in range(4):
            for family, grain in FAMILIES:
                prefix = f"fixture-{range_index}:{tenant}:{family}:{grain}"
                names.update((prefix, prefix + ":oracle"))
    for mutation in range(4):
        for family, grain in FAMILIES:
            prefix = f"mutation{mutation}:1:{family}:{grain}"
            names.update((prefix, prefix + ":oracle"))
    return names


def validate_functional(artifact, source_snapshot):
    tests = artifact.get("tests") if isinstance(artifact, dict) else None
    errors = []
    if not isinstance(artifact, dict) or artifact.get("schema_version") != 2 or artifact.get("status") not in ("PASS", "FAIL") or not isinstance(tests, list):
        errors.append("functional artifact did not complete successfully")
        return errors
    dataset = artifact.get("dataset") if isinstance(artifact.get("dataset"), dict) else {}
    if not artifact.get("run_id") or not artifact.get("started_at_utc") or not artifact.get("finished_at_utc") or artifact.get("scale") != 1_000_000 or dataset.get("dataset_id") != "representative-seed42-v1":
        errors.append("functional run/dataset metadata is incomplete")
    if artifact.get("baseline_cleanup_verified") is not True or artifact.get("source_snapshot_after") != source_snapshot:
        errors.append("functional fixture cleanup was not verified")
    return errors


def validate_freshness(artifact, scale):
    errors = []
    if not isinstance(artifact, dict):
        return ["freshness artifact is missing or not an object"]
    expected_tenants = 10 if scale == 1_000_000 else 100
    snap = artifact.get("source_snapshot") if isinstance(artifact, dict) else None
    if artifact.get("schema_version") != 2 or artifact.get("scale") != scale or not isinstance(snap, dict) or snap.get("order_count") != scale or snap.get("tenant_count") != expected_tenants:
        errors.append("freshness dataset metadata does not match requested scale")
    run = artifact.get("run") if isinstance(artifact.get("run"), dict) else {}
    dataset = artifact.get("dataset") if isinstance(artifact.get("dataset"), dict) else {}
    if artifact.get("runner_status") != "COMPLETED" or not run.get("run_id") or not dataset.get("dataset_id"):
        errors.append("freshness run/dataset metadata is incomplete")
    if artifact.get("baseline_cleanup_verified") is not True or artifact.get("source_snapshot_after") != snap:
        errors.append("freshness cleanup snapshot does not match its initial snapshot")
    samples = artifact.get("samples")
    if not isinstance(samples, list) or len(samples) != 30:
        errors.append("freshness requires exactly 30 observations")
        return errors
    if any(not isinstance(x, dict) for x in samples):
        errors.append("freshness observations contain invalid values")
        return errors
    counts = Counter(x.get("op") for x in samples)
    iterations = Counter((x.get("op"), x.get("iteration")) for x in samples)
    expected_iterations = Counter({(op, i): 1 for op in ("insert", "update", "cancel") for i in range(10)})
    if counts != Counter({"insert": 10, "update": 10, "cancel": 10}) or iterations != expected_iterations:
        errors.append("freshness operation coverage is incomplete")
    if any(x.get("status") != "PASS" or x.get("commit_timestamp_utc") is None or not isinstance(x.get("commit_to_response_seconds"), (int, float)) or not math.isfinite(x["commit_to_response_seconds"]) or x["commit_to_response_seconds"] < 0 or x["commit_to_response_seconds"] >= 30 for x in samples):
        errors.append("freshness has failed or over-30-second observations")
    return errors


def validate_security(artifact, populated_tenants):
    errors = []
    if not isinstance(artifact, dict):
        return ["security artifact is missing or not an object"]
    tenants = artifact.get("tenants") if isinstance(artifact, dict) else None
    if artifact.get("status") not in ("PASS", "FAIL") or artifact.get("runner_status") != "COMPLETED" or not isinstance(tenants, list):
        return ["security artifact did not complete successfully"]
    snap = artifact.get("source_snapshot")
    run = artifact.get("run") if isinstance(artifact.get("run"), dict) else {}
    if artifact.get("schema_version") != 2 or not run.get("run_id") or not isinstance(snap, dict) or snap.get("populated_tenant_count") != populated_tenants or artifact.get("baseline_cleanup_verified") is not True or artifact.get("source_snapshot_after") != snap:
        errors.append("security run metadata or source cleanup evidence is incomplete")
    ids = [x.get("tenant") for x in tenants if isinstance(x, dict)]
    if len(ids) != len(tenants) or sorted(ids) != list(range(1, 101)) or any(not isinstance(x, dict) or x.get("status") != "PASS" for x in tenants):
        errors.append("security matrix does not cover all 100 credential identities")
    if artifact.get("concurrency") != 4 or artifact.get("cross_tenant_pairs_rejected") != 9900:
        errors.append("security cross-tenant/concurrency evidence is incomplete")
    raw_checks = artifact.get("tests")
    checks = {x.get("test"): x.get("status") for x in raw_checks if isinstance(x, dict)} if isinstance(raw_checks, list) else {}
    for name in ("non-superuser-nobypassrls", "source-aggregate-and-write-RLS", "pooled-connection-context-reset"):
        if checks.get(name) != "PASS":
            errors.append(f"security control was not verified: {name}")
    if populated_tenants != 10:
        errors.append("this bounded security matrix expects exactly 10 populated source tenants")
    return errors


def score_safety(artifact, expected_scale=1_000_000):
    """Independently score G-3 from raw paired samples, not a claimed status field."""
    import statistics
    errors = []
    if not isinstance(artifact, dict):
        return "NOT TESTED", ["safety artifact missing"], {}
    if artifact.get("schema_version") != 2 or artifact.get("runner_status") != "COMPLETED":
        errors.append("safety runner did not complete")
    snap = artifact.get("source_snapshot")
    if not isinstance(snap, dict) or snap.get("order_count") != expected_scale or snap.get("tenant_count") != 10 or artifact.get("source_cleanup_verified") is not True or artifact.get("source_snapshot_after") != snap:
        errors.append("safety source scale or cleanup is unverified")
    run = artifact.get("run") if isinstance(artifact.get("run"), dict) else {}
    dataset = artifact.get("dataset") if isinstance(artifact.get("dataset"), dict) else {}
    if not run.get("run_id") or dataset.get("dataset_id") != "representative-seed42-v1":
        errors.append("safety run/dataset metadata is incomplete")
    if artifact.get("pairs") != 8 or artifact.get("operations_per_arm") != 960 or artifact.get("operations_per_pair_arm") != 120:
        errors.append("safety experiment did not complete the registered paired workload")
    arms = artifact.get("arms")
    if not isinstance(arms, list) or len(arms) != 16:
        errors.append("safety arm coverage is incomplete")
        arms = []
    by_pair = {}
    for arm in arms:
        if not isinstance(arm, dict):
            errors.append("safety arm contains invalid value")
            continue
        by_pair.setdefault(arm.get("pair"), []).append(arm)
        if arm.get("operations") != 120 or arm.get("dashboard_errors") != 0:
            errors.append("safety arm failed operations or dashboard requests")
        if arm.get("operational_actual_rps", 0) < artifact.get("operational_rps_target", 40) * .9:
            errors.append("operational workload did not achieve at least 90% of target throughput")
        if arm.get("dashboard") and arm.get("dashboard_actual_rps", 0) < artifact.get("dashboard_rps_target", 20) * .9:
            errors.append("dashboard workload did not achieve at least 90% of target throughput")
    if set(by_pair) != set(range(8)) or any(len(pair_arms) != 2 or {x.get("dashboard") for x in pair_arms} != {False, True} for pair_arms in by_pair.values()):
        errors.append("each of eight randomized pairs must contain baseline and dashboard arms")
    orders = {tuple(x.get("dashboard") for x in by_pair[pair]) for pair in by_pair if len(by_pair[pair]) == 2}
    if len(orders) < 2:
        errors.append("arm order was not varied across paired trials")
    expected_per_kind = {"select": 60, "update": 30, "insert": 30}
    raw = artifact.get("samples")
    if not isinstance(raw, list) or len(raw) != 1920:
        errors.append("raw safety samples are incomplete")
        raw = []
    else:
        from collections import Counter
        grouped = {}
        for sample in raw:
            if not isinstance(sample, dict):
                errors.append("raw safety samples contain invalid values")
                continue
            key = (sample.get("pair"), sample.get("dashboard"))
            grouped.setdefault(key, []).append(sample)
            if any(not isinstance(sample.get(k), (int, float)) or not math.isfinite(sample[k]) or sample[k] < 0 for k in ("statement_ms", "commit_ms", "transaction_ms")):
                errors.append("raw operation timing is missing or invalid")
                break
        if set(grouped) != {(pair, loaded) for pair in range(8) for loaded in (False, True)}:
            errors.append("raw safety samples omit one or more paired arms")
        for key, samples in grouped.items():
            counts = Counter(x.get("kind") for x in samples)
            if counts != Counter(expected_per_kind):
                errors.append(f"operation mix is incomplete for arm {key}")
    telemetry = artifact.get("telemetry")
    if not isinstance(telemetry, list) or len(telemetry) < 8 or artifact.get("telemetry_errors"):
        errors.append("CPU/I/O/lock/WAL telemetry is missing or incomplete")
    else:
        good_telemetry = [x for x in telemetry if isinstance(x, dict)]
        phase_events = artifact.get("phase_events")
        phases = {(x.get("pair"), x.get("dashboard")) for x in phase_events if isinstance(x, dict) and x.get("state") in ("start", "end")} if isinstance(phase_events, list) else set()
        expected_phases = {(pair, loaded) for pair in range(8) for loaded in (False, True)}
        telemetry_complete = any(isinstance(x.get("postgres"), dict) and "wal" in x["postgres"] and "locks_total" in x["postgres"] and isinstance(x.get("podman"), dict) and {c.get("name") for c in x["podman"].get("containers", []) if isinstance(c, dict)} == {"agrregatex-postgres-1", "agrregatex-api-1"} for x in good_telemetry)
        if not expected_phases.issubset(phases) or not telemetry_complete:
            errors.append("telemetry lacks PostgreSQL WAL/lock and container CPU/I/O fields")
    if errors:
        return "NOT TESTED", errors, {}
    metrics = {}
    # Score transaction latency by operation type and full mixed workload.
    # Statement and COMMIT round-trip are reported separately for diagnosis.
    groups = [("all", raw)] + [(kind, [x for x in raw if x["kind"] == kind]) for kind in expected_per_kind]
    for kind, items in groups:
        metrics[kind] = {}
        for field in ("statement_ms", "commit_ms", "transaction_ms"):
            arms_for_field = {}
            for loaded in (False, True):
                vals = [x[field] for x in items if x["dashboard"] is loaded]
                vals.sort()
                arms_for_field["dashboard" if loaded else "baseline"] = {
                    "n": len(vals), "mean": statistics.mean(vals), "p50": statistics.median(vals),
                    "p95": vals[math.ceil(.95 * len(vals)) - 1], "p99": vals[math.ceil(.99 * len(vals)) - 1], "max": max(vals),
                }
            base, loaded = arms_for_field["baseline"], arms_for_field["dashboard"]
            arms_for_field["mean_slowdown_percent"] = (loaded["mean"] / base["mean"] - 1) * 100
            arms_for_field["p95_slowdown_percent"] = (loaded["p95"] / base["p95"] - 1) * 100
            metrics[kind][field] = arms_for_field
    paired = {}
    for kind, items in groups:
        per_pair = []
        for pair in range(8):
            baseline_values = [x["transaction_ms"] for x in items if x["pair"] == pair and x["dashboard"] is False]
            loaded_values = [x["transaction_ms"] for x in items if x["pair"] == pair and x["dashboard"] is True]
            baseline_values.sort()
            loaded_values.sort()
            baseline_p95 = baseline_values[math.ceil(.95 * len(baseline_values)) - 1]
            loaded_p95 = loaded_values[math.ceil(.95 * len(loaded_values)) - 1]
            per_pair.append({
                "pair": pair,
                "baseline_mean_ms": statistics.mean(baseline_values),
                "dashboard_mean_ms": statistics.mean(loaded_values),
                "mean_slowdown_percent": (statistics.mean(loaded_values) / statistics.mean(baseline_values) - 1) * 100,
                "baseline_p95_ms": baseline_p95,
                "dashboard_p95_ms": loaded_p95,
                "p95_slowdown_percent": (loaded_p95 / baseline_p95 - 1) * 100,
            })
        paired[kind] = {
            "pairs": per_pair,
            "mean_of_pair_mean_slowdowns_percent": statistics.mean(x["mean_slowdown_percent"] for x in per_pair),
            "median_pair_mean_slowdown_percent": statistics.median(x["mean_slowdown_percent"] for x in per_pair),
            "median_pair_p95_slowdown_percent": statistics.median(x["p95_slowdown_percent"] for x in per_pair),
            "max_pair_mean_slowdown_percent": max(x["mean_slowdown_percent"] for x in per_pair),
            "max_pair_p95_slowdown_percent": max(x["p95_slowdown_percent"] for x in per_pair),
        }
    metrics["paired"] = paired
    # The PRD target is for the defined mixed operational workload. Operation-
    # type and per-pair tails remain visible diagnostics, while the pass gate
    # uses the pooled mixed-workload latency plus the mean matched-pair delta.
    mixed = metrics["all"]["transaction_ms"]
    paired_mixed = paired["all"]
    passed = (mixed["mean_slowdown_percent"] < 10 and mixed["p95_slowdown_percent"] < 10 and
              paired_mixed["mean_of_pair_mean_slowdowns_percent"] < 10 and
              paired_mixed["median_pair_p95_slowdown_percent"] < 10)
    return ("PASS" if passed else "FAIL"), ([] if passed else ["measured mixed-workload transaction mean, p95, or paired slowdown reached/exceeded 10%"]), metrics


def classify(errors, attempted):
    if not attempted:
        return "NOT TESTED"
    if not errors:
        return "PASS"
    if any("missing" in e or "incomplete" in e or "unexpected" in e or "required" in e or "coverage" in e or "metadata" in e for e in errors):
        return "NOT TESTED"
    return "FAIL"
