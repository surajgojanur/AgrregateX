"""Offline evidence validator. JSON assertions cannot independently certify an official run."""
import argparse
import hashlib
import json
import math
from pathlib import Path

STREAMS = {'st_day_product_status', 'st_day_category_status', 'st_hour_category_status'}
SCENARIOS = {f'{endpoint}/{tenant}/{window}' for endpoint in ('summary', 'trends', 'top-products', 'breakdown')
             for tenant in ('min', 'median', 'max') for window in ('1d', '7d', '30d', 'partial')}
CASES = {
    'FR-1': {'totals', 'empty', 'partial'},
    'FR-2': {'hour', 'day', 'boundaries', 'offset'},
    'FR-3': {'top10', 'ties', 'cross_day'},
    'FR-4': {'status', 'category', 'category_change'},
    'FR-5': {'anonymous', 'invalid_cookie', 'cross_tenant', 'rls', 'connection_reuse'},
    'FR-6': {'insert', 'update', 'cancel', 'delete', 'historical', 'rollback'},
    'FR-7': {'http', 'errors', 'schema'},
}


def number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _verdict(e, evidence_dir=None):
    result = {k: 'NOT TESTED' for k in [*CASES, *(f'G-{i}' for i in range(1, 6))]}
    root = Path(evidence_dir).resolve() if evidence_dir is not None else None
    artifacts = e.get('artifacts', {})
    checked_artifacts = {}

    def live(record):
        if not isinstance(record, dict) or record.get('source') != 'live' or root is None:
            return False
        a = artifacts.get(record.get('artifact'), {})
        if not isinstance(a, dict) or not isinstance(a.get('path'), str):
            return False
        path = (root / a['path']).resolve()
        if not path.is_relative_to(root) or not path.is_file() or path.stat().st_size == 0:
            return False
        if path.stat().st_size > 64*1024*1024:
            return False
        if path not in checked_artifacts:
            checked_artifacts[path] = hashlib.sha256(path.read_bytes()).hexdigest()
        return checked_artifacts[path] == a.get('sha256')

    runs = e.get('runs', {})

    def run_ok(run_id, orders=10000000, tenants=100):
        r = runs.get(run_id, {})
        return (live(r) and r.get('orders') == orders and r.get('populated_tenants') == tenants
                and all(isinstance(r.get(k), str) and r[k] for k in
                        ('hardware', 'image_digest', 'git_sha', 'workload', 'config_sha256', 'dataset_sha256'))
                and r.get('dataset_kind') == 'organizer' and r.get('execution') == 'measured')

    def rows_ok(rows):
        return isinstance(rows, list) and bool(rows) and all(isinstance(r, dict) for r in rows)

    def samples(row, field, limit, minimum=200):
        values = row.get(field, [])
        return (isinstance(values, list) and len(values) >= minimum
                and all(number(v) and 0 <= v < limit for v in values)
                and type(row.get('errors')) is int and row['errors'] == 0
                and type(row.get('timeouts')) is int and row['timeouts'] == 0)

    for key, expected in CASES.items():
        rows = e.get('functional', {}).get(key, [])
        if rows:
            result[key] = 'VERIFIED' if (rows_ok(rows) and {r.get('case') for r in rows} == expected
                and len(rows) == len(expected) and all(live(r) and r.get('execution') == 'real_sql_http'
                and isinstance(r.get('expected'), dict) and bool(r['expected'])
                and r.get('comparison') == 'independent_sql_or_security_assertion'
                and live(runs.get(r.get('run_id'), {}))
                and runs[r['run_id']].get('execution') == 'measured'
                and r.get('actual') == r.get('expected') for r in rows)) else 'FAILED'

    # Flat legacy arrays cannot establish coverage, even if every supplied timing is fast.
    latency = e.get('latency_cases', [])
    if latency or e.get('http_ms'):
        result['G-1'] = 'VERIFIED' if (rows_ok(latency) and len(latency) == len(SCENARIOS)
            and {r.get('scenario') for r in latency} == SCENARIOS
            and all(live(r) and run_ok(r.get('run_id')) and samples(r, 'http_ms', 200) for r in latency)) else 'FAILED'
    fresh = e.get('freshness_cases', [])
    if fresh or e.get('commit_visible_seconds'):
        result['G-2'] = 'VERIFIED' if (rows_ok(fresh) and {r.get('mutation') for r in fresh} == {'insert', 'update', 'cancel', 'historical', 'delete'}
            and len(fresh) == 5 and all(live(r) and run_ok(r.get('run_id'))
                and r.get('method') == 'commit_to_visible_exact_values' and r.get('sustained_writes') is True
                and samples(r, 'seconds', 30, 20) for r in fresh)) else 'FAILED'
    pairs = e.get('safety_pairs', [])
    safety = []
    if pairs:
        valid = rows_ok(pairs) and len(pairs) >= 5 and len({p.get('pair_id') for p in pairs}) == len(pairs)
        for p in pairs if rows_ok(pairs) else []:
            metrics = all(number(p.get(k)) and p[k] > 0 for k in ('baseline_ms', 'dashboard_ms', 'baseline_tps', 'dashboard_tps'))
            if metrics:
                safety.append({'pair_id': p.get('pair_id'), 'latency_slowdown_pct': (p['dashboard_ms']/p['baseline_ms']-1)*100,
                               'throughput_regression_pct': (1-p['dashboard_tps']/p['baseline_tps'])*100})
            valid = valid and metrics and live(p) and run_ok(p.get('run_id')) and p.get('matched_workload') is True and p.get('latency_statistic') == 'transaction_p95'
            valid = valid and all(type(p.get(k)) is int and p[k] >= 200 for k in ('baseline_transactions', 'dashboard_transactions'))
            valid = valid and number(p.get('duration_s')) and p['duration_s'] >= 20 and p.get('errors') == 0 and p.get('timeouts') == 0
        result['G-3'] = 'VERIFIED' if valid and all(r['latency_slowdown_pct'] < 10 and r['throughput_regression_pct'] < 10 for r in safety) else 'FAILED'
    oracles = e.get('oracle_runs', [])
    if oracles or e.get('oracle_mismatches'):
        valid = rows_ok(oracles) and bool(e.get('shards')) and {r.get('shard') for r in oracles} == set(e['shards']) and len(oracles) == len(e['shards'])
        for r in oracles if rows_ok(oracles) else []:
            tables = r.get('tables', [])
            valid = valid and live(r) and run_ok(r.get('run_id')) and r.get('quiesced') is True and rows_ok(tables) and len(tables) == 3 and {t.get('name') for t in tables} == STREAMS and all(
                type(t.get(k)) is int and t[k] == 0 for t in tables for k in ('missing_in_st', 'extra_in_st'))
        result['G-4'] = 'VERIFIED' if valid else 'FAILED'
    growth = e.get('growth_pairs', [])
    if growth:
        valid = rows_ok(growth) and len(growth) == len(SCENARIOS) and {r.get('scenario') for r in growth} == SCENARIOS
        for p in growth if rows_ok(growth) else []:
            a, b = runs.get(p.get('run_1m'), {}), runs.get(p.get('run_10m'), {})
            valid = valid and live(p) and run_ok(p.get('run_1m'),1000000,10) and run_ok(p.get('run_10m')) and all(a.get(k) == b.get(k) for k in ('hardware','image_digest','git_sha','workload','config_sha256')) and p.get('measurement') == 'http_p95_nearest_rank' and samples(p,'samples_1m',float('inf')) and samples(p,'samples_10m',float('inf'))
            if valid:
                a95 = sorted(p['samples_1m'])[math.ceil(len(p['samples_1m'])*.95)-1]
                b95 = sorted(p['samples_10m'])[math.ceil(len(p['samples_10m'])*.95)-1]
                valid = a95 > 0 and b95 < 2*a95
        result['G-5'] = 'VERIFIED' if valid else 'FAILED'
    candidate = all(v == 'VERIFIED' for v in result.values())
    return {'scope': 'official-scale/unreviewed' if candidate else 'representative/unqualified',
            'requirements': result, 'automated_candidate_pass': candidate, 'official_pass': False,
            'qualification_note': 'Offline JSON and artifact hashes cannot prove authentic execution or organizer provenance. Independent review is required; this tool never grants official qualification.',
            'safety_metrics': safety, 'evidence': e}


def verdict(e, evidence_dir=None):
    try:
        if not isinstance(e, dict):
            raise TypeError('Evidence must be an object')
        return _verdict(e, evidence_dir)
    except (TypeError, ValueError, KeyError, OSError, AttributeError):
        return {'scope': 'invalid/unqualified', 'requirements': {k: 'FAILED' for k in [*CASES, *(f'G-{i}' for i in range(1,6))]},
                'official_pass': False, 'automated_candidate_pass': False,
                'validation_error': 'Malformed evidence or unreadable artifact; no qualification granted.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence')
    args = parser.parse_args()
    path = Path(args.evidence)
    report = verdict(json.loads(path.read_text()), path.parent)
    print(json.dumps(report, indent=2, allow_nan=False))
    raise SystemExit(0 if report['official_pass'] else 1)
