"""Bounded read-only HTTP sampler. Smoke evidence never grants official acceptance."""
import argparse
import http.cookiejar
import ipaddress
import json
import math
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from acceptance import SCENARIOS


def percentile(values, fraction):
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


def statistics(rows, elapsed):
    values = [r['ms'] for r in rows if r['ok']]
    return dict(samples=len(rows), successful=len(values), errors=sum(not r['ok'] for r in rows),
                timeouts=sum(r['timeout'] for r in rows), p50_ms=percentile(values, .5),
                p95_ms=percentile(values, .95), p99_ms=percentile(values, .99),
                mean_ms=sum(values)/len(values) if values else None,
                min_ms=min(values) if values else None, max_ms=max(values) if values else None,
                completed_rps=len(rows)/elapsed if elapsed > 0 else None)


def target(url):
    u = urllib.parse.urlsplit(url)
    # Numeric addresses avoid DNS rebinding; redirects are independently refused.
    if u.scheme != 'http' or u.username or u.password or u.path not in ('', '/') or u.query or u.fragment:
        raise ValueError('Use an HTTP loopback origin without credentials/path/query')
    if not u.hostname or not ipaddress.ip_address(u.hostname).is_loopback or not u.port:
        raise ValueError('Explicit numeric loopback address and port required')
    return url.rstrip('/')


def metadata(record, base):
    required = ('approval_reference', 'git_sha', 'image_digest', 'hardware', 'config_sha256',
                'dataset_sha256', 'dataset_seed', 'database_identity', 'project', 'preflight_utc')
    if not isinstance(record, dict) or any(not isinstance(record.get(k), str) or not record[k] for k in required):
        raise ValueError('Incomplete disposable run provenance')
    if (record.get('base') != base or record.get('orders') not in (10000, 100000, 1000000)
            or record.get('populated_tenants') != 10 or record.get('dataset_kind') != 'synthetic'
            or record.get('disposable') is not True or record.get('preflight_pass') is not True):
        raise ValueError('Wrong target/dataset or unapproved preflight')
    for key, length in [('git_sha', 40), ('config_sha256', 64), ('dataset_sha256', 64)]:
        if len(record[key]) != length or any(c not in '0123456789abcdef' for c in record[key]):
            raise ValueError('Invalid provenance checksum')
    return record


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Redirect refused')


def scenarios(tenants, anchor):
    start = datetime.fromisoformat(anchor.replace('Z', '+00:00'))
    if start.utcoffset() != timedelta(0) or len(tenants) != 3 or any(t <= 0 for t in tenants):
        raise ValueError('Three positive tenant IDs and UTC anchor required')
    for name in sorted(SCENARIOS):
        family, size, window = name.split('/')
        tenant = tenants[('min', 'median', 'max').index(size)]
        a = start + (timedelta(hours=13, minutes=7, seconds=11) if window == 'partial' else timedelta())
        b = a + (timedelta(hours=29, seconds=17) if window == 'partial' else timedelta(days=int(window[:-1])))
        params = {'from': a.isoformat(), 'to': b.isoformat()}
        if family == 'trends':
            params['grain'] = 'hour' if window in ('1d', 'partial') else 'day'
        if family == 'breakdown':
            params['by'] = 'status' if window in ('1d', 'partial') else 'category'
        yield dict(scenario=name, tenant=tenant, family=family,
                   path=f'/api/tenants/{tenant}/{family}?' + urllib.parse.urlencode(params))


def sample(opener, base, case, timeout):
    begin = time.perf_counter_ns()
    row = dict(scenario=case['scenario'], status=None, ok=False, timeout=False)
    try:
        with opener.open(base + case['path'], timeout=timeout) as response:
            row['status'] = response.status
            payload = json.loads(response.read(2_000_001))
        key, kind = {'summary': ('summary', dict), 'trends': ('points', list),
                     'top-products': ('products', list), 'breakdown': ('rows', list)}[case['family']]
        row['ok'] = (row['status'] == 200 and isinstance(payload, dict)
                     and payload.get('tenant_id') == case['tenant']
                     and isinstance(payload.get(key), kind) and not payload.get('partial_total', False))
        row['response'] = payload
        if not row['ok']:
            row['error'] = 'identity/schema/partial response failure'
    except urllib.error.HTTPError as exc:
        row.update(status=exc.code, error='HTTP error')
    except (TimeoutError, socket.timeout):
        row.update(timeout=True, error='timeout')
    except urllib.error.URLError as exc:
        row.update(timeout=isinstance(exc.reason, TimeoutError), error='transport error')
    except (ValueError, OSError, TypeError) as exc:
        row['error'] = type(exc).__name__
    row['ms'] = (time.perf_counter_ns() - begin) / 1e6
    return row


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--tenants', nargs=3, type=int, required=True, help='SQL-verified min median max')
    p.add_argument('--anchor', default='2026-09-01T00:00:00Z')
    p.add_argument('--samples', type=int, default=1, help='per scenario; maximum 2 for preserved demo')
    p.add_argument('--cases', type=int, default=4, help='evenly spaced canonical scenarios')
    p.add_argument('--warmup', type=int, default=1, help='total requests')
    p.add_argument('--timeout', type=float, default=2)
    p.add_argument('--allow-auth-bypass-smoke', action='store_true')
    p.add_argument('--approved-disposable-metadata', type=Path,
                   help='Operator-approved provenance JSON; unlocks up to 10,000 serial requests. Never creates a stack.')
    args = p.parse_args()
    base = target(args.base)
    provenance = metadata(json.loads(args.approved_disposable_metadata.read_text()), base) if args.approved_disposable_metadata else None
    if provenance and args.allow_auth_bypass_smoke:
        p.error('Disposable scale measurements require a real session cookie')
    budget = 10000 if provenance else 50
    if not (1 <= args.samples <= (1000 if provenance else 2) and 1 <= args.cases <= 48
            and 0 <= args.warmup <= (48 if provenance else 2)
            and args.samples * args.cases + args.warmup <= budget and 0 < args.timeout <= 5):
        p.error('Request budget exceeded (smoke 50, approved disposable 10000); serial, <=5s timeout')
    matrix = list(scenarios(args.tenants, args.anchor))
    cases = [matrix[i * len(matrix) // args.cases] for i in range(args.cases)]
    args.out.mkdir(parents=True, exist_ok=False)
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                        urllib.request.HTTPCookieProcessor(jar))
    # Default refuses an operator bypass. Secure runs may supply an actual cookie via environment.
    if not args.allow_auth_bypass_smoke:
        try:
            with opener.open(base + '/api/auth/me', timeout=args.timeout):
                p.error('Anonymous identity succeeded: auth enforcement not established')
        except urllib.error.HTTPError as exc:
            if exc.code != 401:
                raise
        cookie = os.environ.get('AX_SESSION_COOKIE')
        if not cookie:
            p.error('Actual AX_SESSION_COOKIE required, or explicit auth-bypass smoke label')
        opener.addheaders = [('Cookie', 'ax_session=' + cookie)]
        with opener.open(base + '/api/auth/me', timeout=args.timeout) as response:
            identity = json.load(response)
    else:
        with opener.open(base + '/api/auth/me', timeout=args.timeout) as response:
            identity = json.load(response)
    if identity.get('user', {}).get('role') != 'admin':
        p.error('Matrix requires verified operator identity')
    warmup = [sample(opener, base, cases[i % len(cases)], args.timeout) for i in range(args.warmup)]
    rows = []
    begin = time.perf_counter()
    for case in cases:
        for _ in range(args.samples):
            rows.append(sample(opener, base, case, args.timeout))
            time.sleep(.1)  # <=10 offered requests/s, concurrency one
    elapsed = time.perf_counter() - begin
    report = dict(scope='representative synthetic measurement' if provenance else 'small-demo read-only smoke; not G1 qualification', official_pass=False,
                  provenance=provenance,
                  automated_candidate_pass=False, auth_bypass_smoke=args.allow_auth_bypass_smoke,
                  utc=datetime.now(timezone.utc).isoformat(), base=base, identity=identity,
                  concurrency=1, offered_rate_cap_rps=10, elapsed_s=elapsed,
                  percentile='nearest rank ceil(p*n); successful responses only',
                  scenarios=cases, warmup=warmup, samples=rows, summary=statistics(rows, elapsed),
                  per_scenario={case['scenario']: statistics(
                      [r for r in rows if r['scenario'] == case['scenario']], elapsed)
                      for case in cases},
                  goals={f'G{i}': 'NOT TESTED' for i in range(1, 6)})
    (args.out / 'http.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    (args.out / 'HTTP.md').write_text('# Bounded HTTP smoke\n\nNot an official G1 result.\n\n```json\n' +
                                   json.dumps(report['summary'], indent=2) + '\n```\n')
    print(json.dumps(report['summary']))
    return int(any(not r['ok'] for r in rows + warmup))


if __name__ == '__main__':
    raise SystemExit(main())
