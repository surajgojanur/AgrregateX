"""Compare saved HTTP answers with independent raw-source recomputation and exact SQL oracle.

Explicit container required. Executes only a bounded READ ONLY transaction; never installs SQL.
Run without concurrent writers: HTTP capture and SQL snapshot are separate observations.
"""
import argparse
from collections import defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess

from acceptance import STREAMS


def reconciliation_ok(rows):
    return (isinstance(rows, list) and len(rows) == 3
            and all(isinstance(r, dict) for r in rows)
            and {r.get('stream_table') for r in rows} == STREAMS
            and all(type(r.get(k)) is int and r[k] == 0
                    for r in rows for k in ('missing_in_st', 'extra_in_st')))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--container', required=True)
    p.add_argument('--http', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    if not args.container.replace('-', '').replace('_', '').isalnum():
        p.error('Invalid container name')
    capture = json.loads(args.http.read_text())
    if len(capture['samples']) > 10000:
        p.error('Capture too large')
    oracle = (Path(__file__).parents[1] / 'sql/30_oracle.sql').read_text()
    oracle = oracle.split('AS $f$\n', 1)[1].split('\n$f$;', 1)[0].rstrip(';')
    # Deliberately bounded small-demo comparator; scale SQL must use grouped source queries.
    sql = """BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='2s';
SELECT json_build_object('orders', (SELECT json_agg(o) FROM
 (SELECT tenant_id,created_at,product_id,status,quantity,unit_price_cents
  FROM ax.orders ORDER BY tenant_id,order_id LIMIT 10001) o),
 'products', (SELECT json_agg(p) FROM (SELECT tenant_id,product_id,category_id FROM ax.products) p),
 'identity', current_database(), 'snapshot', txid_current_snapshot()::text,
 'timestamp', current_timestamp);
SELECT json_agg(r) FROM (""" + oracle + ") r(stream_table, missing_in_st, extra_in_st);\nROLLBACK;\n"
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'executed.sql').write_text(sql)
    proc = subprocess.run(['docker', 'exec', '-i', args.container, 'psql', '-X', '-qAt',
                           '-U', 'postgres', '-d', 'aggregatex', '-v', 'ON_ERROR_STOP=1'],
                          input=sql, text=True, capture_output=True, timeout=15)
    if proc.returncode:
        (args.out / 'error.txt').write_text(proc.stderr)
        raise SystemExit('Read-only SQL failed; see error.txt')
    decoder = json.JSONDecoder()
    raw = proc.stdout.strip()
    source, end = decoder.raw_decode(raw)
    reconciliation = json.loads(raw[end:].strip())
    if len(source['orders']) >= 10001:
        raise SystemExit('Refusing truncated source: this comparator is limited to <=10k rows')
    categories = {(r['tenant_id'], r['product_id']): r['category_id'] for r in source['products']}
    cases = {r['scenario']: r for r in capture['scenarios']}
    comparisons = []
    for row in capture['samples']:
        case = cases[row['scenario']]
        from urllib.parse import parse_qs, urlsplit
        params = parse_qs(urlsplit(case['path']).query)
        a, b = [datetime.fromisoformat(params[k][0]) for k in ('from', 'to')]
        orders = [o for o in source['orders'] if o['tenant_id'] == case['tenant']
                  and a <= datetime.fromisoformat(o['created_at']) < b]
        groups = defaultdict(lambda: [0, 0, 0])
        family = case['family']
        for o in orders:
            sale = o['status'] not in ('cancelled', 'refunded')
            if family == 'summary' or (family == 'breakdown' and params['by'][0] == 'status'):
                key = o['status']
            elif family == 'top-products':
                if not sale:
                    continue
                key = o['product_id']
            elif family == 'breakdown':
                key = categories[(o['tenant_id'], o['product_id'])]
            else:
                dt = datetime.fromisoformat(o['created_at']).replace(minute=0, second=0, microsecond=0)
                key = (dt.replace(hour=0) if params['grain'][0] == 'day' else dt).isoformat()
            g = groups[key]
            g[0] += 1
            g[1] += o['quantity'] if sale or family == 'summary' or params.get('by') == ['status'] else 0
            g[2] += o['quantity'] * o['unit_price_cents'] if sale or family == 'summary' or params.get('by') == ['status'] else 0
        payload = row.get('response', {})
        if family == 'summary':
            actual = {k: [v['orders'], v['units'], v['gross_cents']] for k, v in payload.get('summary', {}).get('by_status', {}).items()}
            expected = dict(groups)
        elif family == 'trends':
            actual = {v['bucket']: [v['orders'], v['sales_cents']] for v in payload.get('points', [])}
            expected = {k: [v[0], v[2]] for k, v in groups.items()}
        elif family == 'top-products':
            actual = [[v['product_id'], v['orders'], v['units_sold'], v['sales_cents']] for v in payload.get('products', [])]
            expected = [[k, *v] for k, v in sorted(groups.items(), key=lambda kv: (-kv[1][2], kv[0]))[:10]]
        else:
            cents = 'gross_cents' if params['by'] == ['status'] else 'sales_cents'
            actual = {str(v['key']): [v['orders'], v['units'], v[cents]] for v in payload.get('rows', [])}
            expected = {str(k): v for k, v in groups.items()}
        comparisons.append(dict(scenario=row['scenario'], match=row['ok'] and actual == expected,
                                actual=actual, expected=expected))
    report = dict(scope='1k smoke; selected numeric fields only; no isolation/tie fixture qualification',
                  database=source['identity'], timestamp=source['timestamp'], snapshot=source['snapshot'],
                  source_orders=len(source['orders']), comparisons=comparisons,
                  failed=sum(not r['match'] for r in comparisons), reconciliation=reconciliation,
                  sql_sha256=hashlib.sha256(sql.encode()).hexdigest(), official_pass=False,
                  quiescence='No writer container observed; external writers not controlled; no quiescence guarantee')
    (args.out / 'comparison.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'comparisons'}))
    return int(report['failed'] > 0 or not reconciliation_ok(reconciliation))


if __name__ == '__main__':
    raise SystemExit(main())
