#!/usr/bin/env python3
"""Audit checked-in representative 1M/10M scale evidence without PostgreSQL.

This validates internal artifact consistency. JSON and hashes cannot establish that
the recorded requests or database observations actually occurred.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

ENDPOINTS = {"summary", "trends", "top_products", "breakdown"}
ROLES = {"largest", "median", "smallest"}
WINDOWS = {"1h", "1d", "7d", "30d", "90d", "partial_7d"}
STREAM_TABLES = {"st_day_product_status", "st_day_category_status", "st_hour_category_status"}
EXPECTED = {(endpoint, role, window) for endpoint in ENDPOINTS for role in ROLES for window in WINDOWS}


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _scenario_key(row):
    return row.get("endpoint"), row.get("tenant_role"), row.get("window")


def _scenario_audit(path, expected_orders, expected_tenants):
    rows = _json(path)
    if not isinstance(rows, list):
        raise ValueError(f"{path}: scenarios must be a JSON array")
    keys = [_scenario_key(row) for row in rows if isinstance(row, dict)]
    findings = []
    seen = set()
    duplicates = sorted({key for key in keys if key in seen or seen.add(key)})
    missing = sorted(EXPECTED - set(keys))
    unexpected = sorted(set(keys) - EXPECTED)
    if len(rows) != len(EXPECTED) or duplicates or missing or unexpected or len(keys) != len(rows):
        findings.append({"status": "FAILED", "detail": "Scenario identity/coverage mismatch.",
                         "count": len(rows), "duplicates": duplicates, "missing": missing, "unexpected": unexpected})
        return rows, findings, None

    sample_sum = error_sum = 0
    great = good = 0
    worst = None
    row_errors = []
    role_metadata = {}
    for row in rows:
        key = _scenario_key(row)
        role_values = (row.get("tenant_id"), row.get("tenant_orders"))
        if type(role_values[0]) is not int or type(role_values[1]) is not int or role_values[1] <= 0:
            row_errors.append({"scenario": key, "error": "missing tenant identity/size provenance"})
        if key[1] in role_metadata and role_metadata[key[1]] != role_values:
            row_errors.append({"scenario": key, "error": "tenant role maps to inconsistent tenant/size"})
        role_metadata[key[1]] = role_values
        n = row.get("n")
        counts = row.get("status_counts")
        if type(n) is not int or n <= 0 or not isinstance(counts, dict) or any(
            not isinstance(status, str) or type(count) is not int or count < 0 for status, count in counts.items()
        ):
            row_errors.append({"scenario": key, "error": "invalid sample/status counts"})
            continue
        sample_sum += n
        status_total = sum(counts.values())
        errors = row.get("errors")
        if type(errors) is not int or errors < 0 or status_total != n or (errors == 0 and set(counts) != {"200"}):
            row_errors.append({"scenario": key, "error": "invalid errors or status count does not equal n"})
        error_sum += errors if type(errors) is int and errors >= 0 else 0
        metrics = [row.get(name) for name in ("p50", "p95", "p99", "max", "mean")]
        if not all(_finite(v) and v >= 0 for v in metrics):
            row_errors.append({"scenario": key, "error": "non-finite or negative latency"})
            continue
        p50, p95, p99, maximum, mean = metrics
        if not (p50 <= p95 <= p99 <= maximum and mean <= maximum):
            row_errors.append({"scenario": key, "error": "latency metrics are not ordered/bounded"})
        great += p95 < 200
        good += p95 < 1000
        if worst is None or p95 > worst["p95_ms"]:
            worst = {"scenario": key, "p95_ms": p95, "tenant_id": row.get("tenant_id"),
                     "tenant_orders": row.get("tenant_orders")}
    if row_errors:
        findings.append({"status": "FAILED", "detail": "Invalid scenario records.", "examples": row_errors[:10]})
    else:
        expected_requests = len(EXPECTED) * 50
        findings.append({"status": "VALIDATED FROM ARTIFACT",
                         "detail": "Scenario dimensions, status counters and aggregate latency values are internally consistent; raw request samples are not present.",
                         "scenarios": len(rows), "requests": sample_sum, "expected_requests_at_50_each": expected_requests,
                         "errors": error_sum, "p95_under_200ms": great, "p95_under_1000ms": good, "worst": worst})
    stats = None if row_errors else {"scenarios": len(rows), "requests": sample_sum, "errors": error_sum,
                                    "great": great, "good": good, "worst": worst}
    return rows, findings, stats


def _audit(evidence_root: Path, source_commit: str):
    """Return a machine-readable artifact audit. No live database is contacted."""
    evidence_root = Path(evidence_root)
    results = evidence_root / "results" if (evidence_root / "results").is_dir() else evidence_root
    one_dir = results / "1m-10t-http"
    ten_dir = results / "10m-100t-http"
    proof = results / "10m-100t-proof"
    out = {"source_pr": 57, "source_commit": source_commit, "official_pass": False,
           "classifications": {}, "g1": {}, "g5": {}, "g4": {}, "dataset": {},
           "qualification_gaps": [], "limitations": []}
    try:
        one_summary = _json(one_dir / "summary.json")
        ten_summary = _json(ten_dir / "summary.json")
        snap = _json(proof / "db-snapshot.json")
        api_oracle = _json(proof / "api-vs-db-100-tenants.json")
        one_rows, one_findings, one_stats = _scenario_audit(one_dir / "scenarios.json", 1_000_000, 10)
        ten_rows, ten_findings, ten_stats = _scenario_audit(ten_dir / "scenarios.json", 10_000_000, 100)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        out["classifications"]["artifact_parse"] = "FAILED"
        out["limitations"].append(f"Required evidence could not be parsed: {exc}")
        return out

    for label, summary, rows, stats, orders, tenants in (
        ("1m", one_summary, one_rows, one_stats, 1_000_000, 10),
        ("10m", ten_summary, ten_rows, ten_stats, 10_000_000, 100),
    ):
        valid = isinstance(summary, dict) and summary.get("orders_total") == orders and summary.get("tenants") == tenants
        valid = valid and len(rows) == len(EXPECTED) and stats is not None
        if valid:
            valid = summary.get("scenarios") == len(rows) and summary.get("requests") == stats["requests"]
            valid = valid and summary.get("errors") == stats["errors"] and summary.get("worst_p95_ms") == stats["worst"]["p95_ms"]
            valid = valid and summary.get("scenarios_p95_under_200ms") == stats["great"]
            valid = valid and summary.get("scenarios_p95_under_1000ms") == stats["good"]
        expected_count = len(rows) * 50
        valid = valid and all(row.get("n") == 50 for row in rows)
        roles = summary.get("roles") if isinstance(summary, dict) else None
        if isinstance(roles, dict):
            for role in ROLES:
                observed = next(((row.get("tenant_id"), row.get("tenant_orders")) for row in rows
                                 if isinstance(row, dict) and row.get("tenant_role") == role), None)
                expected_role = roles.get(role)
                valid = valid and isinstance(expected_role, list) and len(expected_role) == 2 and observed == tuple(expected_role)
        else:
            valid = False
        out["classifications"][f"{label}_scenario_artifact_consistency"] = "VALIDATED FROM ARTIFACT" if valid else "FAILED"
        out["g1"][label] = {"summary": summary, "computed_from_scenarios": stats,
                            "scenario_findings": one_findings if label == "1m" else ten_findings,
                            "expected_requests_from_n": expected_count}

    out["dataset"] = {
        "ten_million_snapshot": {k: snap.get(k) for k in ("captured_at", "version", "pg_trickle", "total_orders", "generated_orders", "distinct_ids", "date_min", "date_max", "days", "db_size", "gen_params", "gen_chunks")},
        "tenant_count": len(snap.get("tenants", [])) if isinstance(snap.get("tenants"), list) else None,
        "tenant_size_min": min((t.get("orders", 0) for t in snap.get("tenants", []) if isinstance(t, dict)), default=None),
        "tenant_size_max": max((t.get("orders", 0) for t in snap.get("tenants", []) if isinstance(t, dict)), default=None),
        "stream_tables": snap.get("stream_tables"),
    }
    gen = snap.get("gen_params") if isinstance(snap, dict) else None
    tenant_rows = snap.get("tenants") if isinstance(snap, dict) else None
    stream_rows = snap.get("stream_tables") if isinstance(snap, dict) else None
    dataset_valid = (snap.get("total_orders") == ten_summary.get("orders_total") == 10_000_000
                     and snap.get("generated_orders") == 10_000_000 and snap.get("distinct_ids") == 10_000_000
                     and isinstance(gen, dict) and gen.get("orders") == 10_000_000 and gen.get("tenants") == 100
                     and gen.get("seed") == 42 and isinstance(tenant_rows, list) and len(tenant_rows) == 100
                     and isinstance(stream_rows, list) and {r.get("name") for r in stream_rows if isinstance(r, dict)} == STREAM_TABLES)
    out["classifications"]["10m_dataset_snapshot_consistency"] = "VALIDATED FROM ARTIFACT" if dataset_valid else "FAILED"
    out["classifications"]["dataset_execution_authenticity"] = "REPORTED BUT NOT INDEPENDENTLY RECOMPUTABLE"
    out["classifications"]["matched_run_provenance"] = "INSUFFICIENT EVIDENCE"
    out["classifications"]["g1_threshold_arithmetic"] = (
        "VALIDATED FROM ARTIFACT" if one_stats is not None and ten_stats is not None else "FAILED"
    )
    out["classifications"]["g1_percentile_source"] = "REPORTED BUT NOT INDEPENDENTLY RECOMPUTABLE"
    out["classifications"]["g1_official_qualification"] = "INSUFFICIENT EVIDENCE"
    out["classifications"]["g2_10m_freshness"] = "NOT TESTED"
    out["classifications"]["g3_10m_write_safety"] = "NOT TESTED"
    out["classifications"]["g4_10m_post_mutation"] = "NOT TESTED"
    out["classifications"]["g5_official_qualification"] = "INSUFFICIENT EVIDENCE"

    one_by_key = {_scenario_key(row): row for row in one_rows if isinstance(row, dict)}
    ten_by_key = {_scenario_key(row): row for row in ten_rows if isinstance(row, dict)}
    growth = _json(ten_dir / "growth_vs_1m.json")
    ratios = growth.get("ratios") if isinstance(growth, dict) else None
    growth_findings = []
    growth_results = []
    if not isinstance(ratios, list):
        growth_findings.append("FAILED: growth ratios missing or malformed")
    else:
        keys = [(r.get("endpoint"), r.get("role"), r.get("window")) for r in ratios if isinstance(r, dict)]
        duplicates = len(keys) != len(set(keys))
        missing = sorted(EXPECTED - set(keys))
        unexpected = sorted(set(keys) - EXPECTED)
        if duplicates or missing or unexpected or len(keys) != len(EXPECTED):
            growth_findings.append(f"FAILED: matched growth coverage invalid; duplicates={duplicates}, missing={len(missing)}, unexpected={len(unexpected)}")
        else:
            for row in ratios:
                key = (row["endpoint"], row["role"], row["window"])
                lower = one_by_key.get(key)
                upper = ten_by_key.get(key)
                if not lower or not upper or not all(_finite(row.get(k)) and row[k] > 0 for k in ("p95_1m", "p95_10m", "ratio")):
                    growth_findings.append(f"FAILED: incomplete/invalid pair for {key}")
                    continue
                if row["p95_1m"] != lower.get("p95") or row["p95_10m"] != upper.get("p95"):
                    growth_findings.append(f"FAILED: pair p95 does not match scenario artifacts for {key}")
                    continue
                computed = row["p95_10m"] / row["p95_1m"]
                if round(computed, 2) != row["ratio"]:
                    growth_findings.append(f"FAILED: ratio arithmetic mismatch for {key}")
                    continue
                growth_results.append({"key": key, "ratio": computed})
    if growth_results and not growth_findings:
        ratios_computed = [row["ratio"] for row in growth_results]
        sorted_ratios = sorted(ratios_computed)
        median = (sorted_ratios[35] + sorted_ratios[36]) / 2
        counts = {"under_2x": sum(v < 2 for v in ratios_computed), "under_5x": sum(v < 5 for v in ratios_computed)}
        stored_consistent = (growth.get("n") == len(EXPECTED) and growth.get("under_2x") == counts["under_2x"]
                             and growth.get("under_5x") == counts["under_5x"]
                             and growth.get("min") == round(min(ratios_computed), 2)
                             and growth.get("max") == round(max(ratios_computed), 2)
                             and growth.get("median") == round(median, 2))
        out["g5"] = {"matched_scenarios": len(growth_results), "computed": {**counts,
                    "median_ratio_from_stored_p95": round(median, 2),
                    "min_ratio": round(min(ratios_computed), 2), "max_ratio": round(max(ratios_computed), 2),
                    "at_or_over_2x": [list(r["key"]) for r in growth_results if r["ratio"] >= 2],
                    "at_or_over_5x": [list(r["key"]) for r in growth_results if r["ratio"] >= 5]},
                    "stored_summary_consistent": stored_consistent,
                    "classification": "VALIDATED FROM ARTIFACT" if stored_consistent else "FAILED"}
        out["classifications"]["growth_arithmetic"] = out["g5"]["classification"]
        out["classifications"]["growth_percentile_recomputation"] = "REPORTED BUT NOT INDEPENDENTLY RECOMPUTABLE"
    else:
        out["g5"] = {"findings": growth_findings, "classification": "FAILED" if any("FAILED" in x for x in growth_findings) else "INSUFFICIENT EVIDENCE"}
        out["classifications"]["growth_arithmetic"] = out["g5"]["classification"]

    oracle_text = (proof / "oracle-lowmem.txt").read_text(encoding="utf-8")
    oracle_records = []
    for line in oracle_text.splitlines():
        parts = line.strip().split("|")
        if len(parts) == 3:
            oracle_records.append((parts[0], parts[1], parts[2]))
    oracle_valid = (len(oracle_records) == 3 and {name for name, _, _ in oracle_records} == STREAM_TABLES
                    and all(missing == "0" and extra == "0" for _, missing, extra in oracle_records))
    api_valid = (api_oracle.get("all_match") is True and api_oracle.get("mismatches") == []
                 and len(api_oracle.get("rows", [])) == 100
                 and api_oracle.get("api_total") == api_oracle.get("db_total") == 10_000_000)
    out["g4"] = {"initial_load_oracle_lines": oracle_records, "initial_load_exact_oracle_consistent": oracle_valid,
                 "api_vs_db_100_tenants": {"all_match": api_oracle.get("all_match"), "rows": len(api_oracle.get("rows", [])),
                                            "api_total": api_oracle.get("api_total"), "db_total": api_oracle.get("db_total")},
                 "api_oracle_artifact_consistent": api_valid,
                 "post_mutation_correctness": "NOT TESTED — unresolved G4 reducer defect"}
    out["classifications"]["initial_load_oracle_values"] = "VALIDATED FROM ARTIFACT" if oracle_valid and api_valid else "FAILED"
    out["classifications"]["oracle_execution_authenticity"] = "REPORTED BUT NOT INDEPENDENTLY RECOMPUTABLE"

    out["qualification_gaps"] = [
        "Representative synthetic data (seed 42), not organizer data.",
        "50 stored requests per scenario; acceptance protocol requires at least 200 successful HTTP samples per scenario.",
        "Only aggregate p50/p95/p99/max/mean are stored; raw per-request timing samples are absent, so nearest-rank percentiles cannot be independently recomputed.",
        "The 72-case six-window matrix does not itself establish the protocol's complete, exact acceptance matrix unless each named requirement is mapped and approved.",
        "Stored JSON, host logs, counts, and hashes do not independently authenticate database execution or immutable image provenance.",
        "G2 sustained commit-to-visible at 10M: NOT TESTED; G3 write safety at 10M: NOT TESTED.",
        "G4 post-mutation correctness at 10M: NOT TESTED; initial-load oracle does not test incremental updates/cancellations.",
        "G5 is representative synthetic growth evidence, not qualified official acceptance. Tenant matching is by size rank, not same tenant IDs; the largest tenant grew about 5.7x.",
    ]
    out["limitations"] = [
        "The auditor checked artifact relationships and recomputed threshold counts/ratio arithmetic only. It did not contact the database, API, Docker or GitHub Actions.",
        "G1 shows 71/72 stored p95 values below 200 ms and 72/72 below 1,000 ms with 0 stored errors (50 per scenario).",
        "G5 summary arithmetic is recomputable from the stored per-scenario p95 values; percentile derivation from raw request samples is not.",
    ]
    out["recommended_demo_statement"] = (
        "On representative synthetic data, the recorded 10M/100 run completed 3,600 serial HTTP requests across 72 scenarios with 50 samples each and no recorded errors; 71 stored p95 values were below 200 ms and all 72 below 1 s. Stored 10M/1M p95 ratios had median 1.18x, 66 below 2x and 71 below 5x. This is not organizer-data qualification, does not include raw timing samples, and does not establish post-mutation G4 correctness."
    )
    out["do_not_claim"] = ["Official G1/G5 acceptance passed", "All scenarios meet the Great threshold", "10M incremental correctness passed after writes/cancellations", "G2 or G3 passed at 10M", "10M organizer-data compatibility"]
    return out


def audit(evidence_root: Path, source_commit: str):
    try:
        return _audit(evidence_root, source_commit)
    except (OSError, json.JSONDecodeError, TypeError, ValueError, KeyError, AttributeError) as exc:
        return {"source_pr": 57, "source_commit": source_commit, "official_pass": False,
                "classifications": {"artifact_parse": "FAILED"}, "g1": {}, "g5": {}, "g4": {},
                "qualification_gaps": [], "limitations": [f"Malformed or missing artifact: {exc}"]}


def render_markdown(result):
    g1 = result.get("g1", {}).get("10m", {})
    stats = g1.get("computed_from_scenarios") or {}
    g5 = result.get("g5", {}).get("computed") or {}
    lines = [
        "# Independent 10M Scale Evidence Audit",
        "",
        f"Source: PR [#57](https://github.com/surajgojanur/AgrregateX/pull/57), commit `{result.get('source_commit')}`.",
        "Audit method: standard-library parsing and independent arithmetic on checked-in artifact JSON/text; no database or API calls.",
        "",
        "## Artifact facts independently cross-checked",
        "",
        f"- 10M dataset snapshot reports {result.get('dataset', {}).get('ten_million_snapshot', {}).get('total_orders')} rows, {result.get('dataset', {}).get('tenant_count')} tenants, PostgreSQL {result.get('dataset', {}).get('ten_million_snapshot', {}).get('version')}, pg_trickle {result.get('dataset', {}).get('ten_million_snapshot', {}).get('pg_trickle')}, generator seed {result.get('dataset', {}).get('ten_million_snapshot', {}).get('gen_params', {}).get('seed')}.",
        f"- Scenario artifacts enumerate {stats.get('scenarios')} 10M cases and {stats.get('requests')} requests; stored errors total {stats.get('errors')}.",
        f"- Recomputed G1 counts from per-case p95 fields: {stats.get('great')}/72 below 200 ms and {stats.get('good')}/72 below 1,000 ms. Worst recorded p95: {stats.get('worst', {}).get('p95_ms')} ms, {stats.get('worst', {}).get('scenario')}.",
        f"- Matched G5 ratios: {result.get('g5', {}).get('matched_scenarios')} scenarios; median {g5.get('median_ratio_from_stored_p95')}x; {g5.get('under_2x')} below 2x; {g5.get('under_5x')} below 5x; worst {g5.get('max_ratio')}x.",
        f"- Initial-load oracle output contains three stream tables with 0 missing / 0 extra rows: {result.get('g4', {}).get('initial_load_exact_oracle_consistent')}.",
        f"- API/source count artifact reports {result.get('g4', {}).get('api_vs_db_100_tenants', {}).get('rows')} tenant matches, totals {result.get('g4', {}).get('api_vs_db_100_tenants', {}).get('api_total')} vs {result.get('g4', {}).get('api_vs_db_100_tenants', {}).get('db_total')}.",
        "",
        "Evidence paths in the source PR: `hackathon/integration/scale/results/10m-100t-http/{summary.json,scenarios.json,growth_vs_1m.json}`; `10m-100t-proof/{db-snapshot.json,api-vs-db-100-tenants.json,oracle-lowmem.txt}`; plus `1m-10t-http/{summary.json,scenarios.json}`.",
        "",
        "## Evidence limits and qualification",
        "",
    ]
    lines.extend(f"- {gap}" for gap in result.get("qualification_gaps", []))
    lines += ["", "## Reported run incidents and setup", "",
              "- The source report says the init server exceeded its 60-second `pg_ctl` shutdown wait while checkpointing about 4 GB of WAL; the container exited, then recovered by crash replay on restart. The report says no committed data was lost.",
              "- The original all-in-one hashed oracle with `work_mem=128MB` was OOM-killed in a 2 GiB container. A memory-bounded `oracle_lowmem.sql` was used for the later three-table result.",
              "- Both HTTP reports describe auth disabled for the load client, serial requests after warmup, and no concurrent writers. These measurements do not establish authenticated multi-tenant load behavior.",
              "- The report supplies an abbreviated image digest and no complete matched Git/config/dataset fingerprint across both scale arms; strict G5 provenance remains insufficient."]
    lines += ["", "## Status categories", "", "| Check | Audit classification |", "|---|---|"]
    lines.extend(f"| {key} | {value} |" for key, value in result.get("classifications", {}).items())
    lines += ["", "## Judge-safe wording", "", result.get("recommended_demo_statement", "")]
    lines += ["", "Do not claim:", ""]
    lines.extend(f"- {claim}" for claim in result.get("do_not_claim", []))
    lines += ["", "## Next experiment", "", "Repeat the same 1M/10M scenario matrix with at least 200 successful raw HTTP timings per scenario and preserved sample-level latency records; hold host, image digest, code revision, query windows, warmup, and workload constant. Then run separate 10M sustained-write freshness and post-mutation three-table correctness checks after the #54 reducer is validated. Organizer data and approval remain required for official acceptance.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_root", type=Path, help="Scale results directory containing 1m-10t-http, 10m-100t-http and 10m-100t-proof")
    parser.add_argument("--source-commit", default="b0f360685c33f67516c6ef0c1c6170b1575d14ee")
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--markdown-out", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.evidence_root, args.source_commit)
    args.json_out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    args.markdown_out.write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps({"classifications": result["classifications"], "g1_10m": result.get("g1", {}).get("10m", {}).get("computed_from_scenarios"), "g5": result.get("g5", {}), "g4": result.get("g4", {})}, indent=2))
    return 0 if all(value != "FAILED" for value in result["classifications"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
