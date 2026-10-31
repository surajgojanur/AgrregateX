"""Fail-closed acceptance report; input is collected experiment evidence, never estimates."""
import argparse
import json
import math


def verdict(e):
    result = {f"FR-{i}": "NOT TESTED" for i in range(1, 8)}
    result.update({f"G-{i}": "NOT TESTED" for i in range(1, 6)})
    for i in range(1, 8):
        checks = e.get("functional", {}).get(f"FR-{i}", [])
        if checks:
            result[f"FR-{i}"] = "VERIFIED" if all(x is True for x in checks) else "FAILED"
    def number(x):
        return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
    def threshold(key, values, limit):
        if values:
            result[key] = "VERIFIED" if all(number(v) and 0 <= v < limit for v in values) else "FAILED"
    threshold("G-1", e.get("http_ms", []), 200)
    threshold("G-2", e.get("commit_visible_seconds", []), 30)
    pairs = e.get("safety_pairs", [])
    if pairs:
        valid = all(number(p.get("baseline_ms")) and p["baseline_ms"] > 0
                    and number(p.get("dashboard_ms")) and p["dashboard_ms"] > 0
                    and number(p.get("baseline_tps")) and p["baseline_tps"] > 0
                    and number(p.get("dashboard_tps")) and p["dashboard_tps"] > 0 for p in pairs)
        result["G-3"] = "VERIFIED" if valid and len(pairs) >= 5 and all(
            p["dashboard_ms"] / p["baseline_ms"] < 1.1 and
            p["dashboard_tps"] / p["baseline_tps"] > .9 for p in pairs) else "FAILED"
    mismatches = e.get("oracle_mismatches", [])
    if mismatches:
        result["G-4"] = "VERIFIED" if all(number(x) and x == 0 for x in mismatches) else "FAILED"
    growth = e.get("growth_pairs", [])
    if growth:
        result["G-5"] = "VERIFIED" if all(number(p.get("ms_1m")) and p["ms_1m"] > 0
            and number(p.get("ms_10m")) and 0 < p["ms_10m"] < 2 * p["ms_1m"] for p in growth) else "FAILED"
    qualified = (e.get("orders") == 10000000 and e.get("populated_tenants") == 100
                 and e.get("official_dataset_verified") is True)
    return {"scope": "official" if qualified else "representative/unqualified",
            "requirements": result,
            "official_pass": qualified and all(v == "VERIFIED" for v in result.values()),
            "evidence": e}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence")
    args = parser.parse_args()
    report = verdict(json.loads(open(args.evidence).read()))
    print(json.dumps(report, indent=2, allow_nan=False))
    raise SystemExit(0 if report["official_pass"] else 1)
