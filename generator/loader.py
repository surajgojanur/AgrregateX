#!/usr/bin/env python3
"""AgrregateX resumable bulk loader (Phase 01A).

REPRESENTATIVE dataset only: official organizer generator/schema compatibility
is NOT VERIFIED. Generator `representative-v1` reproduces the Phase 00
`generator/load.py` row formula exactly (same seed/hash/tenant mapping).

Pipeline (each step is restartable; re-running `load` continues where it stopped):

  plan      deterministic run id = hash(spec); one open run at a time
  stage     server-side generation into loader.stage_orders in independent
            batch transactions; each batch commits rows + rollup deltas +
            checkpoint atomically. No live table is touched.
  verify    counts, contiguity, fingerprints, reference domain, delta totals
  activate  ONE transaction: write-block orders (readers continue on the old
            snapshot), copy staged rows, add deltas to rollups, mark active.
            Readers see either the old or the new dataset, never a mix.
  finalize  VACUUM/ANALYZE

Rollups are additive signed sums, so merging staged deltas is exact even if API
writes happened on `orders` before activation; no full-source GROUP BY rebuild
is needed. `verify-rollups` (full reconciliation) and `rebuild-rollups` (shadow
table + atomic rename) are separate repair/audit commands.

Connection: --dsn, else $ADMIN_DATABASE_URL, else $LOADER_DSN, else the
repository .env (agrregatex_owner on 127.0.0.1:25432). The DSN is never printed.
"""
import argparse, hashlib, json, os, re, resource, shutil, signal, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MIGRATIONS = HERE / 'migrations'
RESULTS = HERE / 'results'
LOCK_KEY = 4_157_204_001          # session advisory lock: one loader process per database
FULL_SCALE_ROWS = 1_000_000       # anything above needs the integration gate
GATE_ENV = 'AGRREGATEX_LOADER_ALLOW_FULL_SCALE'
EXIT_REFUSED, EXIT_CONFLICT, EXIT_INJECTED, EXIT_STOPPED = 2, 3, 75, 130

try:
    import psycopg
    from psycopg import sql as pgsql
except ImportError:  # pragma: no cover
    psycopg = pgsql = None


class Refused(Exception):
    """Precondition not met; nothing was changed."""


class Conflict(Exception):
    """Existing data disagrees with the deterministic spec; nothing was changed."""


class InjectedFailure(Exception):
    """Test hook."""


# ----------------------------------------------------------------- generators
# A generator returns SQL that yields the stage columns for ordinals
# %(a)s..%(b)s. Add the official organizer generator here once supplied.
STAGE_COLS = 'ordinal,tenant_id,customer_id,product_id,category_id,ordered_at,status,quantity,unit_price_cents'
PRODUCTS_PER_TENANT, CUSTOMERS_PER_TENANT, CATEGORIES = 32, 100, 8


def gen_representative_v1(seed, tenants):
    s = [int(seed) + k for k in range(7)]
    t = int(tenants)
    m = '9223372036854775807'
    return f"""SELECT i AS ordinal,
 CASE WHEN h<400000 THEN 1 WHEN h<600000 THEN 2 ELSE 3+(h%%{t - 2})::int END AS tenant_id,
 1+(hc%%{CUSTOMERS_PER_TENANT})::int AS customer_id,
 1+(hp%%{PRODUCTS_PER_TENANT})::int AS product_id,
 1+((hp%%{PRODUCTS_PER_TENANT})::int%%{CATEGORIES}) AS category_id,
 '2026-08-03 00:00:00+00'::timestamptz+make_interval(secs=>(ht%%7776000)::double precision) AS ordered_at,
 CASE WHEN hs%%10=0 THEN 'cancelled' WHEN hs%%10<5 THEN 'shipped' ELSE 'placed' END AS status,
 1+(hq%%4)::int AS quantity, 100+(hm%%50000) AS unit_price_cents
FROM (SELECT i,(hashtextextended(i::text,{s[0]})&{m})%%1000000 h,
 (hashtextextended(i::text,{s[1]})&{m}) hc,(hashtextextended(i::text,{s[2]})&{m}) hp,
 (hashtextextended(i::text,{s[3]})&{m}) ht,(hashtextextended(i::text,{s[4]})&{m}) hs,
 (hashtextextended(i::text,{s[5]})&{m}) hq,(hashtextextended(i::text,{s[6]})&{m}) hm
 FROM generate_series(%(a)s::bigint,%(b)s::bigint) i) x"""


GENERATORS = {'representative-v1': gen_representative_v1}


def fp(alias, ordinal):
    """Order-independent row fingerprint term (sum over rows, numeric => no overflow)."""
    a = alias
    return (f"hashtextextended(concat_ws('|',{ordinal},{a}.tenant_id,{a}.customer_id,{a}.product_id,"
            f"{a}.category_id,extract(epoch FROM {a}.ordered_at),{a}.status,{a}.quantity,{a}.unit_price_cents),0)::numeric")


# ----------------------------------------------------------------- utilities
def resolve_dsn(arg):
    if arg:
        return arg
    for k in ('ADMIN_DATABASE_URL', 'LOADER_DSN'):
        if os.environ.get(k):
            return os.environ[k]
    env = ROOT / '.env'
    if env.exists():
        vals = dict(l.split('=', 1) for l in env.read_text().splitlines() if '=' in l and not l.startswith('#'))
        if 'DB_PASSWORD' in vals:
            return f"postgresql://agrregatex_owner:{vals['DB_PASSWORD'].strip()}@127.0.0.1:25432/agrregatex"
    raise Refused('no database DSN: pass --dsn, set ADMIN_DATABASE_URL, or run scripts/setup.sh')


def loader_commit():
    import subprocess
    try:
        sha = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], capture_output=True, text=True,
                             timeout=5).stdout.strip()
        dirty = subprocess.run(['git', '-C', str(ROOT), 'status', '--porcelain', '--', 'generator'],
                               capture_output=True, text=True, timeout=5).stdout.strip()
        return (sha + ('-dirty' if dirty else '')) or None
    except Exception:
        return None


def rss_bytes():
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r if sys.platform == 'darwin' else r * 1024


def log(msg, **kv):
    extra = ' '.join(f'{k}={v}' for k, v in kv.items())
    print(f'[loader {time.strftime("%H:%M:%S")}] {msg}' + (f' {extra}' if extra else ''), file=sys.stderr, flush=True)


class Loader:
    def __init__(self, dsn, hooks=None):
        if psycopg is None:
            raise Refused("psycopg is not installed: python3 -m pip install 'psycopg[binary]==3.2.3'")
        self.conn = psycopg.connect(dsn, autocommit=True, application_name='agrregatex-loader')
        self.hooks = hooks or {}
        self.stop_requested = False
        self.x("SET TIME ZONE 'UTC'")
        self.x('SET statement_timeout=0')
        self.x("SET idle_in_transaction_session_timeout=0")
        # If this client dies mid-batch, the server aborts the orphaned statement within ~1s
        # (PG >= 14) instead of finishing it while still holding the loader lock.
        try:
            self.x("SET client_connection_check_interval='1s'")
        except Exception:
            pass

    # -- db helpers
    def x(self, q, p=None):
        return self.conn.execute(q, p)

    def one(self, q, p=None):
        return self.conn.execute(q, p).fetchone()

    def val(self, q, p=None):
        r = self.one(q, p)
        return None if r is None else r[0]

    def lsn(self):
        return self.val('SELECT pg_current_wal_insert_lsn()::text')

    def wal_since(self, start):
        return int(self.val('SELECT pg_wal_lsn_diff(pg_current_wal_insert_lsn(),%s::pg_lsn)', (start,)))

    def backend_mem(self):
        try:
            return int(self.val('SELECT sum(total_bytes) FROM pg_backend_memory_contexts'))
        except Exception:
            return None

    def checkpoints(self):
        for q in ('SELECT num_timed+num_requested FROM pg_stat_checkpointer',
                  'SELECT checkpoints_timed+checkpoints_req FROM pg_stat_bgwriter'):
            try:
                with self.conn.transaction():
                    return int(self.val(q))
            except Exception:
                continue
        return None

    def lock_process(self, wait_seconds=30):
        deadline = time.monotonic() + wait_seconds
        while not self.val('SELECT pg_try_advisory_lock(%s)', (LOCK_KEY,)):
            if time.monotonic() >= deadline:
                h = self.one("SELECT a.pid,a.application_name,a.state,now()-a.xact_start FROM pg_locks l JOIN "
                             "pg_stat_activity a USING (pid) WHERE l.locktype='advisory' AND l.objid=%s AND l.granted",
                             (LOCK_KEY & 0xFFFFFFFF,))
                raise Refused('another loader session holds the loader lock' +
                              (f' (pid={h[0]} app={h[1]} state={h[2]} xact_age={h[3]}); if its client was killed the '
                               'server aborts it shortly, then re-run' if h else ''))
            time.sleep(0.5)

    def hook(self, name, at=None):
        v = self.hooks.get(name)
        if v is None or (at is not None and v != at):
            return
        if name == 'crash_in_batch':
            log('TEST HOOK: hard process exit inside open batch transaction')
            os._exit(137)
        raise InjectedFailure(f'test hook {name}')

    # -- schema
    def init(self):
        with self.conn.transaction():
            for f in sorted(MIGRATIONS.glob('*.sql')):
                self.x(f.read_text())
        return {'schema_version': self.val('SELECT max(version) FROM loader.schema_version')}

    def require_schema(self):
        if not self.val("SELECT to_regclass('loader.runs') IS NOT NULL"):
            raise Refused('loader schema missing: run `init` first')

    # -- runs
    def get_run(self, run_id=None):
        self.require_schema()
        q = ('SELECT run_id,spec,state,first_ordinal,last_ordinal,batch_size,total_batches,verification,activation,'
             'created_at,activated_at FROM loader.runs ')
        if run_id:
            r = self.one(q + 'WHERE run_id=%s', (run_id,))
        else:
            r = self.one(q + "WHERE state NOT IN ('active','aborted') LIMIT 1") or \
                self.one(q + 'ORDER BY updated_at DESC LIMIT 1')
        if r is None:
            return None
        keys = ['run_id', 'spec', 'state', 'first_ordinal', 'last_ordinal', 'batch_size', 'total_batches',
                'verification', 'activation', 'created_at', 'activated_at']
        return dict(zip(keys, r))

    @staticmethod
    def make_spec(a):
        spec = {'generator': a.generator, 'seed': a.seed, 'rows': a.rows, 'tenants': a.tenants,
                'prefix_rows': a.prefix_rows, 'prefix_tenants': a.prefix_tenants if a.prefix_rows else None,
                'batch_size': a.batch_size,
                'dataset': 'REPRESENTATIVE; official organizer compatibility NOT VERIFIED'}
        if spec['generator'] not in GENERATORS:
            raise Refused(f'unknown generator {spec["generator"]}')
        if spec['tenants'] < 3 or (spec['prefix_tenants'] is not None and spec['prefix_tenants'] < 3):
            raise Refused('representative-v1 needs >= 3 tenants')
        if not 0 <= spec['prefix_rows'] < spec['rows']:
            raise Refused('need 0 <= prefix_rows < rows')
        if not 1 <= spec['batch_size'] <= 1_000_000:
            raise Refused('batch size must be 1..1000000')
        if spec['rows'] > FULL_SCALE_ROWS and not (a.allow_full_scale and os.environ.get(GATE_ENV) == '1'):
            raise Refused(f'{spec["rows"]} rows exceeds the bounded-test limit {FULL_SCALE_ROWS}; full-scale loads '
                          f'are gated: pass --allow-full-scale AND set {GATE_ENV}=1 only after integration approval')
        return spec

    def plan(self, spec):
        self.require_schema()
        canon = json.dumps({k: v for k, v in spec.items() if k != 'dataset'}, sort_keys=True)
        run_id = 'r' + hashlib.sha256(canon.encode()).hexdigest()[:16]
        first, last = spec['prefix_rows'] + 1, spec['rows']
        total = -(-(last - first + 1) // spec['batch_size'])
        with self.conn.transaction():
            self.x('LOCK TABLE loader.runs IN EXCLUSIVE MODE')
            existing = self.get_run(run_id)
            other = self.one("SELECT run_id,state FROM loader.runs WHERE state NOT IN ('active','aborted') AND run_id<>%s",
                             (run_id,))
            if other:
                raise Refused(f'run {other[0]} is {other[1]}; finish it or `abort --run {other[0]}` first')
            if existing and existing['state'] != 'aborted':
                return existing
            if self.val('SELECT EXISTS(SELECT 1 FROM loader.stage_orders)') or \
               self.val('SELECT EXISTS(SELECT 1 FROM loader.delta_daily) OR EXISTS(SELECT 1 FROM loader.delta_hourly)'):
                raise Refused('staging tables are not empty but no run owns them; inspect, then `abort`')
            if existing:  # re-plan an aborted run
                self.x("UPDATE loader.runs SET state='planned',verification=NULL,activation=NULL,updated_at=clock_timestamp() "
                       "WHERE run_id=%s", (run_id,))
            else:
                self.x('INSERT INTO loader.runs(run_id,spec,state,first_ordinal,last_ordinal,batch_size,total_batches) '
                       "VALUES (%s,%s,'planned',%s,%s,%s,%s)",
                       (run_id, json.dumps(spec), first, last, spec['batch_size'], total))
        return self.get_run(run_id)

    def committed_batches(self, run_id):
        return {r[0] for r in self.x('SELECT batch_no FROM loader.batches WHERE run_id=%s', (run_id,)).fetchall()}

    # -- stage
    def stage(self, run, max_batches=None):
        spec = run['spec']
        gen = GENERATORS[spec['generator']](spec['seed'], spec['tenants'])
        sql = f"""WITH gen AS MATERIALIZED ({gen}),
ins AS (INSERT INTO loader.stage_orders({STAGE_COLS}) SELECT {STAGE_COLS} FROM gen
        ON CONFLICT (ordinal) DO NOTHING RETURNING 1),
dd AS (INSERT INTO loader.delta_daily AS d
        SELECT tenant_id,date_trunc('day',ordered_at,'UTC'),product_id,category_id,status,
               count(*),sum(quantity),sum(quantity::bigint*unit_price_cents)
        FROM gen GROUP BY 1,2,3,4,5
        ON CONFLICT (tenant_id,bucket,product_id,category_id,status)
        DO UPDATE SET n=d.n+excluded.n,units=d.units+excluded.units,cents=d.cents+excluded.cents RETURNING 1),
dh AS (INSERT INTO loader.delta_hourly AS d
        SELECT tenant_id,date_trunc('hour',ordered_at,'UTC'),category_id,status,
               count(*),sum(quantity),sum(quantity::bigint*unit_price_cents)
        FROM gen GROUP BY 1,2,3,4
        ON CONFLICT (tenant_id,bucket,category_id,status)
        DO UPDATE SET n=d.n+excluded.n,units=d.units+excluded.units,cents=d.cents+excluded.cents RETURNING 1)
SELECT (SELECT count(*) FROM gen),(SELECT count(*) FROM ins),
       (SELECT coalesce(sum({fp('g', 'g.ordinal')}),0) FROM gen g),
       (SELECT coalesce(sum(quantity),0) FROM gen),(SELECT coalesce(sum(quantity::bigint*unit_price_cents),0) FROM gen),
       (SELECT count(*) FROM dd),(SELECT count(*) FROM dh)"""
        done = self.committed_batches(run['run_id'])
        todo = [b for b in range(run['total_batches']) if b not in done]
        log('stage', run=run['run_id'], committed=len(done), remaining=len(todo), batch_size=run['batch_size'])
        stats = {'batches_committed_now': 0, 'rows_committed_now': 0, 'seconds': 0.0, 'wal_bytes': 0,
                 'peak_backend_mem_bytes': 0, 'checkpoints_before': self.checkpoints()}
        t_start = time.monotonic()
        for b in todo:
            if self.stop_requested:
                log('graceful stop requested; last batch committed, exiting')
                raise KeyboardInterrupt
            if max_batches is not None and stats['batches_committed_now'] >= max_batches:
                break
            a = run['first_ordinal'] + b * run['batch_size']
            z = min(run['last_ordinal'], a + run['batch_size'] - 1)
            t0 = time.monotonic()
            with self.conn.transaction():
                # Serialize on the run row; re-check checkpoint under the lock (retry safety).
                state = self.val('SELECT state FROM loader.runs WHERE run_id=%s FOR UPDATE', (run['run_id'],))
                if state not in ('planned', 'staging'):
                    raise Refused(f'run is {state}; cannot stage')
                if self.val('SELECT 1 FROM loader.batches WHERE run_id=%s AND batch_no=%s', (run['run_id'], b)):
                    continue
                w0 = self.lsn()
                generated, inserted, fprint, units, cents, dg, hg = self.one(sql, {'a': a, 'b': z})
                if inserted != generated:
                    raise Conflict(f'batch {b} ({a}..{z}): {generated - inserted} staged rows already exist without a '
                                   'checkpoint; staging was modified outside the loader. Transaction rolled back; '
                                   'run `abort` and re-plan.')
                self.hook('crash_in_batch', stats['batches_committed_now'] + 1)
                wal = self.wal_since(w0)
                ms = round((time.monotonic() - t0) * 1000, 1)
                self.x('INSERT INTO loader.batches(run_id,batch_no,first_ordinal,last_ordinal,row_count,fingerprint,units,'
                       'cents,daily_groups,hourly_groups,elapsed_ms,wal_bytes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                       (run['run_id'], b, a, z, generated, fprint, units, cents, dg, hg, ms, wal))
                self.x("UPDATE loader.runs SET state='staging',updated_at=clock_timestamp() WHERE run_id=%s", (run['run_id'],))
            stats['batches_committed_now'] += 1
            stats['rows_committed_now'] += generated
            stats['wal_bytes'] += wal
            m = self.backend_mem() or 0
            stats['peak_backend_mem_bytes'] = max(stats['peak_backend_mem_bytes'], m)
            n_done = len(done) + stats['batches_committed_now']
            if n_done % 10 == 0 or n_done == run['total_batches']:
                log('checkpoint', batch=f'{n_done}/{run["total_batches"]}', last_ordinal=z, batch_ms=ms,
                    rows_per_s=round(generated / max(ms / 1000, 1e-9)))
            if self.hooks.get('fail_after_batches') == stats['batches_committed_now']:
                raise InjectedFailure('test hook fail_after_batches')
        stats['seconds'] = round(time.monotonic() - t_start, 3)
        stats['checkpoints_after'] = self.checkpoints()
        stats['python_peak_rss_bytes'] = rss_bytes()
        if len(self.committed_batches(run['run_id'])) == run['total_batches']:
            with self.conn.transaction():
                self.x("UPDATE loader.runs SET state='staged',updated_at=clock_timestamp() "
                       "WHERE run_id=%s AND state IN ('planned','staging')", (run['run_id'],))
        return stats

    # -- verify staged data
    def verify_stage(self, run):
        spec, rid = run['spec'], run['run_id']
        t0 = time.monotonic()
        with self.conn.transaction():
            state = self.val('SELECT state FROM loader.runs WHERE run_id=%s FOR UPDATE', (rid,))
            if state not in ('staged', 'verified'):
                raise Refused(f'run is {state}; stage must complete before verification')
            b = self.one('SELECT count(*),coalesce(sum(row_count),0),coalesce(sum(fingerprint),0),coalesce(sum(units),0),'
                         'coalesce(sum(cents),0),count(*) FILTER (WHERE first_ordinal<>%s+batch_no*%s OR '
                         'last_ordinal<>least(%s,%s+(batch_no+1)*%s-1)) FROM loader.batches WHERE run_id=%s',
                         (run['first_ordinal'], run['batch_size'], run['last_ordinal'], run['first_ordinal'],
                          run['batch_size'], rid))
            s = self.one(f"""SELECT count(*),min(ordinal),max(ordinal),coalesce(sum({fp('s', 's.ordinal')}),0),
 coalesce(sum(quantity),0),coalesce(sum(quantity::bigint*unit_price_cents),0),
 count(*) FILTER (WHERE tenant_id NOT BETWEEN 1 AND %s OR customer_id NOT BETWEEN 1 AND {CUSTOMERS_PER_TENANT}
   OR product_id NOT BETWEEN 1 AND {PRODUCTS_PER_TENANT} OR category_id<>1+((product_id-1)%%{CATEGORIES}))
FROM loader.stage_orders s""", (spec['tenants'],))
            dd = self.one('SELECT coalesce(sum(n),0),coalesce(sum(units),0),coalesce(sum(cents),0),count(*) FROM loader.delta_daily')
            dh = self.one('SELECT coalesce(sum(n),0),coalesce(sum(units),0),coalesce(sum(cents),0),count(*) FROM loader.delta_hourly')
            expected = run['last_ordinal'] - run['first_ordinal'] + 1
            checks = {
                'batches_complete': b[0] == run['total_batches'],
                'batches_contiguous': b[5] == 0,
                'batch_rows_equal_expected': b[1] == expected,
                'stage_rows_equal_expected': s[0] == expected,
                'stage_ordinal_range': (s[1], s[2]) == (run['first_ordinal'], run['last_ordinal']),
                'stage_fingerprint_equals_checkpoints': s[3] == b[2],
                'stage_units_cents_equal_checkpoints': (s[4], s[5]) == (b[3], b[4]),
                'references_in_domain': s[6] == 0,
                'delta_daily_totals': (dd[0], dd[1], dd[2]) == (expected, s[4], s[5]),
                'delta_hourly_totals': (dh[0], dh[1], dh[2]) == (expected, s[4], s[5]),
            }
            result = {'checks': checks, 'rows': s[0], 'fingerprint': str(s[3]), 'units': int(s[4]), 'cents': int(s[5]),
                      'delta_daily_rows': dd[3], 'delta_hourly_rows': dh[3], 'seconds': round(time.monotonic() - t0, 3),
                      'passed': all(checks.values())}
            if result['passed']:
                self.x("UPDATE loader.runs SET state='verified',verification=%s,updated_at=clock_timestamp() WHERE run_id=%s",
                       (json.dumps(result, default=str), rid))
        if not result['passed']:
            raise Conflict('stage verification failed: ' + json.dumps({k: v for k, v in checks.items() if not v}))
        return result

    # -- activate
    def activate(self, run, mode='incremental', lock_timeout='10s', prefix_check='fingerprint'):
        spec, rid = run['spec'], run['run_id']
        P = spec['prefix_rows']
        steps, t_all = {}, time.monotonic()

        def step(name, q, p=None):
            t = time.monotonic()
            r = self.x(q, p)
            steps[name] = round(time.monotonic() - t, 3)
            return r

        w0, ck0, commit = self.lsn(), self.checkpoints(), loader_commit()
        with self.conn.transaction():
            self.x(f"SET LOCAL lock_timeout='{check_timeout(lock_timeout)}'")
            state = self.val('SELECT state FROM loader.runs WHERE run_id=%s FOR UPDATE', (rid,))
            if state == 'active':
                return {'already_active': True}
            if state != 'verified':
                raise Refused(f'run is {state}; activation requires a verified stage')
            # Writers block; readers (ACCESS SHARE) keep reading the pre-activation snapshot.
            lockmode = 'ACCESS EXCLUSIVE' if mode == 'rebuild-index' else 'EXCLUSIVE'
            step('lock', f'LOCK TABLE public.orders, public.daily_product, public.hourly_category IN {lockmode} MODE')
            # Provenance: existing bulk rows must be exactly the declared prefix.
            bulk = step('prefix_count', 'SELECT count(*) FROM public.orders WHERE id<0').fetchone()[0]
            if bulk != P:
                raise Conflict(f'orders has {bulk} bulk (negative-id) rows; spec declares prefix_rows={P}')
            if P and prefix_check == 'fingerprint':
                gen = GENERATORS[spec['generator']](spec['seed'], spec['prefix_tenants'])
                exp = step('prefix_expected', f'SELECT coalesce(sum({fp("g", "g.ordinal")}),0) FROM ({gen}) g',
                           {'a': 1, 'b': P}).fetchone()[0]
                got = step('prefix_actual', f'SELECT coalesce(sum({fp("o", "-o.id")}),0) FROM public.orders o WHERE id<0').fetchone()[0]
                if exp != got:
                    raise Conflict('existing bulk rows differ from the declared prefix spec (modified, or a different '
                                   'generator/seed/tenants). Use --prefix-check count to accept them knowingly.')
            T = spec['tenants']
            step('references', f"""INSERT INTO public.tenants SELECT i,'Store '||i FROM generate_series(1,{T}) i ON CONFLICT DO NOTHING;
INSERT INTO public.products SELECT t,i,1+(i-1)%{CATEGORIES},'Product '||i FROM generate_series(1,{T}) t
 CROSS JOIN generate_series(1,{PRODUCTS_PER_TENANT}) i ON CONFLICT DO NOTHING;
INSERT INTO public.customers SELECT t,i FROM generate_series(1,{T}) t
 CROSS JOIN generate_series(1,{CUSTOMERS_PER_TENANT}) i ON CONFLICT DO NOTHING""")
            idx = []
            if mode == 'rebuild-index':
                idx = self.x("SELECT indexrelid::regclass::text,pg_get_indexdef(indexrelid) FROM pg_index "
                             "WHERE indrelid='public.orders'::regclass AND NOT indisprimary AND NOT indisunique").fetchall()
                for name, _ in idx:
                    self.x(f'DROP INDEX {name}')
            # Rollups are merged from staged deltas below, so the per-row trigger is
            # skipped for this transaction only (DDL is transactional; on rollback the
            # trigger stays enabled; no other session can write while we hold the lock).
            self.x('ALTER TABLE public.orders DISABLE TRIGGER rollups')
            ins = step('insert_orders', 'INSERT INTO public.orders(tenant_id,id,customer_id,product_id,category_id,ordered_at,'
                       'status,quantity,unit_price_cents,version) SELECT tenant_id,-ordinal,customer_id,product_id,category_id,'
                       'ordered_at,status,quantity,unit_price_cents,1 FROM loader.stage_orders ORDER BY tenant_id,ordered_at')
            inserted = ins.rowcount
            self.x('ALTER TABLE public.orders ENABLE TRIGGER rollups')
            for name, ddl in idx:
                step(f'create_index:{name}', ddl)
            expected = run['last_ordinal'] - run['first_ordinal'] + 1
            if inserted != expected:
                raise Conflict(f'inserted {inserted} rows, expected {expected}')
            step('merge_daily', 'INSERT INTO public.daily_product AS d SELECT * FROM loader.delta_daily ON CONFLICT '
                 '(tenant_id,bucket,product_id,category_id,status) DO UPDATE SET n=d.n+excluded.n,'
                 'units=d.units+excluded.units,cents=d.cents+excluded.cents')
            step('merge_hourly', 'INSERT INTO public.hourly_category AS d SELECT * FROM loader.delta_hourly ON CONFLICT '
                 '(tenant_id,bucket,category_id,status) DO UPDATE SET n=d.n+excluded.n,'
                 'units=d.units+excluded.units,cents=d.cents+excluded.cents')
            self.hook('fail_in_activation', True)
            # Free staging disk in the same commit; checkpoints in loader.batches remain for audit.
            step('truncate_stage', 'TRUNCATE loader.stage_orders, loader.delta_daily, loader.delta_hourly')
            wal = self.wal_since(w0)
            info = {'mode': mode, 'inserted': inserted, 'loader_commit': commit, 'steps_seconds': steps, 'wal_bytes': wal,
                    'transaction_seconds': round(time.monotonic() - t_all, 3), 'prefix_rows': P,
                    'prefix_check': prefix_check if P else None}
            self.x("UPDATE loader.runs SET state='active',activated_at=clock_timestamp(),activation=%s,"
                   'updated_at=clock_timestamp() WHERE run_id=%s', (json.dumps(info, default=str), rid))
        info['commit_total_seconds'] = round(time.monotonic() - t_all, 3)
        info['checkpoints_during'] = None if ck0 is None else (self.checkpoints() or 0) - ck0
        return info

    def finalize(self):
        t = time.monotonic()
        self.x('VACUUM (ANALYZE) public.orders')
        self.x('ANALYZE public.daily_product')
        self.x('ANALYZE public.hourly_category')
        return {'vacuum_analyze_seconds': round(time.monotonic() - t, 3)}

    def sizes(self):
        rows = self.x("""SELECT n.nspname||'.'||c.relname,pg_relation_size(c.oid),pg_indexes_size(c.oid),pg_total_relation_size(c.oid)
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relkind='r' AND
 (n.nspname='loader' OR (n.nspname='public' AND c.relname IN ('orders','daily_product','hourly_category')))
ORDER BY 1""").fetchall()
        return {'database_bytes': self.val('SELECT pg_database_size(current_database())'),
                'relations': {r[0]: {'heap': r[1], 'index': r[2], 'total': r[3]} for r in rows}}

    # -- audit / repair
    # table -> (bucket expression, key columns); semantics identical to maintain_rollups()
    ROLLUPS = {
        'daily_product': ("date_trunc('day',ordered_at,'UTC')", ['tenant_id', 'bucket', 'product_id', 'category_id', 'status']),
        'hourly_category': ("date_trunc('hour',ordered_at,'UTC')", ['tenant_id', 'bucket', 'category_id', 'status']),
    }

    def expected_sql(self, table, tenant=None):
        b, keys = self.ROLLUPS[table]
        sel = ','.join(f'{b} AS bucket' if k == 'bucket' else k for k in keys)
        grp = ','.join(b if k == 'bucket' else k for k in keys)
        where = f' WHERE tenant_id={int(tenant)}' if tenant is not None else ''
        return (f'SELECT {sel},count(*)::bigint n,sum(quantity)::bigint units,'
                f'sum(quantity::bigint*unit_price_cents)::bigint cents FROM public.orders{where} GROUP BY {grp}')

    def verify_rollups(self, tenant=None, sample=5):
        out = {}
        t0 = time.monotonic()
        with self.conn.transaction():
            self.x('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            for table, (_, keylist) in self.ROLLUPS.items():
                keys = ','.join(keylist)
                where = f'WHERE coalesce(e.tenant_id,d.tenant_id)={int(tenant)}' if tenant is not None else 'WHERE true'
                dwhere = f'WHERE tenant_id={int(tenant)}' if tenant is not None else ''
                q = (f'WITH e AS ({self.expected_sql(table, tenant)}), d AS (SELECT * FROM public.{table} {dwhere}) '
                     f'SELECT {", ".join(keylist)},'
                     'coalesce(e.n,0),coalesce(d.n,0),coalesce(e.cents,0),coalesce(d.cents,0) '
                     f'FROM e FULL JOIN d USING ({keys}) {where} AND (coalesce(e.n,0)<>coalesce(d.n,0) OR '
                     'coalesce(e.units,0)<>coalesce(d.units,0) OR coalesce(e.cents,0)<>coalesce(d.cents,0))')
                rows = self.x(q).fetchall()
                out[table] = {'mismatches': len(rows), 'sample': [list(map(str, r)) for r in rows[:sample]]}
            out['source_orders'] = self.val('SELECT count(*) FROM public.orders' +
                                            (f' WHERE tenant_id={int(tenant)}' if tenant is not None else ''))
        out['seconds'] = round(time.monotonic() - t0, 3)
        out['passed'] = all(out[t]['mismatches'] == 0 for t in self.ROLLUPS)
        if tenant is None:
            self.record_validation('verify-rollups', out['passed'], out)
        return out

    def record_validation(self, kind, passed, result):
        if not self.val("SELECT to_regclass('loader.validations') IS NOT NULL"):
            return
        with self.conn.transaction():
            rid = self.val("SELECT run_id FROM loader.runs WHERE state='active' ORDER BY activated_at DESC LIMIT 1")
            self.x('INSERT INTO loader.validations(run_id,kind,passed,result) VALUES (%s,%s,%s,%s)',
                   (rid, kind, passed, json.dumps(result, default=str)))

    def manifest(self):
        self.require_schema()
        if not self.val("SELECT to_regclass('loader.dataset_manifest') IS NOT NULL"):
            raise Refused('manifest view missing: run `init`')
        return self.val('SELECT manifest FROM loader.dataset_manifest')

    def rebuild_rollups(self, lock_timeout='10s'):
        """Shadow rebuild + atomic swap. Writes to orders are paused (EXCLUSIVE lock)
        for the duration; readers keep using the old, consistent rollups until the swap
        commits. RLS, policies, grants and the PK are recreated on the shadow table."""
        info, t0 = {}, time.monotonic()
        with self.conn.transaction():
            self.x(f"SET LOCAL lock_timeout='{check_timeout(lock_timeout)}'")
            self.x('LOCK TABLE public.orders IN EXCLUSIVE MODE')
            for table in self.ROLLUPS:
                t = time.monotonic()
                shadow = f'{table}__shadow'
                self.x(f'DROP TABLE IF EXISTS public.{shadow}')
                self.x(f'CREATE TABLE public.{shadow} (LIKE public.{table} INCLUDING ALL)')
                rls, force = self.one("SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid=%s::regclass",
                                      (f'public.{table}',))
                if rls:
                    self.x(f'ALTER TABLE public.{shadow} ENABLE ROW LEVEL SECURITY')
                if force:
                    self.x(f'ALTER TABLE public.{shadow} FORCE ROW LEVEL SECURITY')
                pols = self.x("SELECT policyname,permissive,roles::text[],cmd,qual,with_check FROM pg_policies "
                              "WHERE schemaname='public' AND tablename=%s", (table,)).fetchall()
                for name, perm, roles, cmd, qual, chk in pols:
                    q = (f'CREATE POLICY {pgsql.Identifier(name).as_string(self.conn)} ON public.{shadow} AS {perm} '
                         f'FOR {cmd} TO {", ".join(pgsql.Identifier(r).as_string(self.conn) if r != "public" else "PUBLIC" for r in roles)}')
                    if qual:
                        q += f' USING ({qual})'
                    if chk:
                        q += f' WITH CHECK ({chk})'
                    self.x(q)
                grants = self.x("SELECT grantee,privilege_type FROM information_schema.role_table_grants WHERE "
                                "table_schema='public' AND table_name=%s AND grantee<>current_user", (table,)).fetchall()
                for grantee, priv in grants:
                    self.x(f'GRANT {priv} ON public.{shadow} TO ' +
                           ('PUBLIC' if grantee == 'PUBLIC' else pgsql.Identifier(grantee).as_string(self.conn)))
                keys = ','.join(self.ROLLUPS[table][1])
                self.x(f'INSERT INTO public.{shadow}({keys},n,units,cents) {self.expected_sql(table)}')
                drift = self.val(f'SELECT count(*) FROM public.{shadow} s FULL JOIN public.{table} d USING ({keys}) WHERE '
                                 'coalesce(s.n,0)<>coalesce(d.n,0) OR coalesce(s.units,0)<>coalesce(d.units,0) OR '
                                 'coalesce(s.cents,0)<>coalesce(d.cents,0)')
                built = time.monotonic() - t
                # Swap: brief ACCESS EXCLUSIVE on the rollup only, held until commit.
                self.x(f'LOCK TABLE public.{table} IN ACCESS EXCLUSIVE MODE')
                self.x(f'DROP TABLE public.{table}')
                self.x(f'ALTER TABLE public.{shadow} RENAME TO {table}')
                for (iname,) in self.x("SELECT indexrelid::regclass::text FROM pg_index WHERE indrelid=%s::regclass",
                                       (f'public.{table}',)).fetchall():
                    bare = iname.split('.')[-1]
                    if shadow in bare:
                        self.x(f'ALTER INDEX public.{bare} RENAME TO {bare.replace(shadow, table)}')
                info[table] = {'rows': self.val(f'SELECT count(*) FROM public.{table}'), 'drift_rows_repaired': drift,
                               'build_seconds': round(built, 3)}
        self.x('ANALYZE public.daily_product')
        self.x('ANALYZE public.hourly_category')
        info['seconds'] = round(time.monotonic() - t0, 3)
        info['source_orders'] = self.val('SELECT count(*) FROM public.orders')
        self.record_validation('rebuild-rollups', True, info)
        return info

    def abort(self, run):
        with self.conn.transaction():
            state = self.val('SELECT state FROM loader.runs WHERE run_id=%s FOR UPDATE', (run['run_id'],))
            if state == 'active':
                raise Refused('run is active; activated data is not removed by the loader')
            self.x('DELETE FROM loader.batches WHERE run_id=%s', (run['run_id'],))
            self.x('TRUNCATE loader.stage_orders, loader.delta_daily, loader.delta_hourly')
            self.x("UPDATE loader.runs SET state='aborted',verification=NULL,updated_at=clock_timestamp() WHERE run_id=%s",
                   (run['run_id'],))
        return {'aborted': run['run_id']}

    def status(self, run_id=None, exact=False):
        self.require_schema()
        run = self.get_run(run_id)
        out = {'schema_version': self.val('SELECT max(version) FROM loader.schema_version'), 'run': None}
        if run:
            b = self.one('SELECT count(*),coalesce(sum(row_count),0),coalesce(sum(elapsed_ms),0),max(last_ordinal),'
                         'coalesce(sum(wal_bytes),0),max(committed_at) FROM loader.batches WHERE run_id=%s', (run['run_id'],))
            rate = b[1] / (float(b[2]) / 1000) if b[2] else None
            remaining = (run['last_ordinal'] - run['first_ordinal'] + 1) - b[1]
            out['run'] = {
                'run_id': run['run_id'], 'state': run['state'], 'spec': run['spec'],
                'batches_committed': b[0], 'total_batches': run['total_batches'], 'rows_staged': b[1],
                'last_committed_ordinal': b[3], 'last_checkpoint_at': str(b[5]) if b[5] else None,
                'stage_rows_per_second': round(rate) if rate else None,
                'stage_eta_seconds': round(remaining / rate) if rate and remaining and run['state'] in ('planned', 'staging') else None,
                'stage_wal_bytes': int(b[4]), 'verification': run['verification'], 'activation': run['activation'],
                'activated_at': str(run['activated_at']) if run['activated_at'] else None,
                'next_step': {'planned': 'stage', 'staging': 'stage (resume)', 'staged': 'verify-stage',
                              'verified': 'activate', 'active': 'none (finalize/verify-rollups optional)',
                              'aborted': 'plan'}[run['state']]}
        if exact:
            out['orders'] = self.val('SELECT count(*) FROM public.orders')
            out['tenants_with_orders'] = self.val('SELECT count(DISTINCT tenant_id) FROM public.orders')
        else:
            out['orders_estimate'] = self.val("SELECT reltuples::bigint FROM pg_class WHERE oid='public.orders'::regclass")
        return out


# ----------------------------------------------------------------------- CLI
def check_timeout(v):
    if not re.fullmatch(r'\d+(ms|s|min)?', v):
        raise Refused(f'invalid lock timeout {v!r}')
    return v


def write_result(name, data):
    try:
        RESULTS.mkdir(exist_ok=True)
        p = RESULTS / f'{name}.json'
        p.write_text(json.dumps(data, indent=2, default=str))
        return str(p)
    except OSError:
        return None


def build_parser():
    ap = argparse.ArgumentParser(prog='generator/loader.py', description=__doc__.split('\n\n')[0])
    ap.add_argument('--dsn', help='admin (table-owner) DSN; never printed')
    ap.add_argument('--lock-wait', type=float, default=30, help='seconds to wait for the loader lock (default 30)')
    sub = ap.add_subparsers(dest='cmd', required=True)

    def spec_args(p):
        p.add_argument('--rows', type=int, required=True, help='total bulk rows the dataset ends with')
        p.add_argument('--tenants', type=int, required=True)
        p.add_argument('--seed', type=int, default=42)
        p.add_argument('--generator', default='representative-v1', choices=sorted(GENERATORS))
        p.add_argument('--batch-size', type=int, default=50_000)
        p.add_argument('--prefix-rows', type=int, default=0,
                       help='bulk rows already present in orders (ordinals 1..P), e.g. the Phase 00 1M baseline')
        p.add_argument('--prefix-tenants', type=int, default=10, help='tenant count the prefix was generated with')
        p.add_argument('--allow-full-scale', action='store_true', help=f'required (with {GATE_ENV}=1) above 1M rows')
        p.add_argument('--min-free-gib', type=float, default=None,
                       help='local free-disk precondition (default 30 GiB above 1M rows, else none)')
        p.add_argument('--disk-path', default=str(ROOT))

    def act_args(p):
        p.add_argument('--mode', choices=['incremental', 'rebuild-index'], default='incremental',
                       help='incremental: readers stay online (default); rebuild-index: drops/recreates secondary '
                            'indexes under ACCESS EXCLUSIVE (readers blocked)')
        p.add_argument('--lock-timeout', default='10s')
        p.add_argument('--prefix-check', choices=['fingerprint', 'count'], default='fingerprint')

    def hooks(p):  # test-only failure injection
        p.add_argument('--fail-after-batches', type=int, help=argparse.SUPPRESS)
        p.add_argument('--crash-in-batch', type=int, help=argparse.SUPPRESS)
        p.add_argument('--fail-in-activation', action='store_true', help=argparse.SUPPRESS)

    sub.add_parser('init', help='apply loader migrations (idempotent)')
    p = sub.add_parser('plan', help='register a run for a spec (idempotent)'); spec_args(p)
    p = sub.add_parser('stage', help='stage remaining batches of the open run (resumable)')
    p.add_argument('--run'); p.add_argument('--max-batches', type=int); hooks(p)
    p = sub.add_parser('verify-stage', help='verify staged rows/checkpoints/deltas'); p.add_argument('--run')
    p = sub.add_parser('activate', help='atomically publish a verified run'); p.add_argument('--run'); act_args(p); hooks(p)
    sub.add_parser('finalize', help='VACUUM ANALYZE source and rollups')
    p = sub.add_parser('load', help='init+plan+stage+verify+activate+finalize; re-run to resume')
    spec_args(p); act_args(p); hooks(p)
    p.add_argument('--max-batches', type=int, help='stop after N batches this invocation (bounded runs)')
    p.add_argument('--verify-rollups', action='store_true', help='full reconciliation after activation (expensive at 10M)')
    p.add_argument('--skip-finalize', action='store_true')
    p = sub.add_parser('status', help='show run progress'); p.add_argument('--run'); p.add_argument('--exact', action='store_true')
    p = sub.add_parser('verify-rollups', help='read-only full reconciliation of rollups vs source')
    p.add_argument('--tenant', type=int)
    p = sub.add_parser('rebuild-rollups', help='shadow rebuild + atomic swap (pauses writes)'); p.add_argument('--lock-timeout', default='10s')
    sub.add_parser('manifest', help='print the dataset manifest (loader.dataset_manifest) for benchmarks')
    p = sub.add_parser('abort', help='discard an unactivated run and its staged data'); p.add_argument('--run')
    return ap


def disk_check(a):
    need = a.min_free_gib if a.min_free_gib is not None else (30 if a.rows > FULL_SCALE_ROWS else 0)
    free = shutil.disk_usage(a.disk_path).free / 1024 ** 3
    if free < need:
        raise Refused(f'{free:.1f} GiB free at {a.disk_path}; require {need} GiB for staging/source/index/WAL headroom')
    return round(free, 1)


def need_run(L, run_id):
    run = L.get_run(run_id)
    if run is None:
        raise Refused('no run found; use `plan` or `load`')
    return run


def main(argv=None):
    a = build_parser().parse_args(argv)
    hooks = {k: getattr(a, k) for k in ('fail_after_batches', 'crash_in_batch', 'fail_in_activation')
             if getattr(a, k, None)}
    L = None
    try:
        L = Loader(resolve_dsn(a.dsn), hooks)

        def on_signal(sig, _):
            if L.stop_requested:
                raise KeyboardInterrupt
            L.stop_requested = True
            log(f'signal {sig}: finishing current batch, then stopping (repeat to abort the open batch)')
        signal.signal(signal.SIGINT, on_signal)
        signal.signal(signal.SIGTERM, on_signal)

        if a.cmd == 'init':
            out = L.init()
        elif a.cmd == 'plan':
            L.lock_process(a.lock_wait); spec = Loader.make_spec(a); disk_check(a); out = L.plan(spec)
        elif a.cmd == 'stage':
            L.lock_process(a.lock_wait); run = need_run(L, a.run); out = L.stage(run, a.max_batches)
            out['status'] = L.status(run['run_id'])['run']
        elif a.cmd == 'verify-stage':
            L.lock_process(a.lock_wait); out = L.verify_stage(need_run(L, a.run))
        elif a.cmd == 'activate':
            L.lock_process(a.lock_wait); out = L.activate(need_run(L, a.run), a.mode, a.lock_timeout, a.prefix_check)
        elif a.cmd == 'finalize':
            L.lock_process(a.lock_wait); out = L.finalize()
        elif a.cmd == 'status':
            out = L.status(a.run, a.exact)
        elif a.cmd == 'verify-rollups':
            out = L.verify_rollups(a.tenant)
        elif a.cmd == 'rebuild-rollups':
            L.lock_process(a.lock_wait); out = L.rebuild_rollups(a.lock_timeout)
        elif a.cmd == 'manifest':
            out = L.manifest()
            if out is None:
                raise Refused('no activated load: manifest is empty')
            out['result_file'] = write_result(f'manifest-{out["run_id"]}', out)
        elif a.cmd == 'abort':
            L.lock_process(a.lock_wait); out = L.abort(need_run(L, a.run))
        elif a.cmd == 'load':
            L.lock_process(a.lock_wait)
            spec = Loader.make_spec(a)
            free = disk_check(a)
            out = {'free_disk_gib_at_start': free, 'init': L.init()}
            run = L.plan(spec)
            out['run_id'] = run['run_id']
            t0 = time.monotonic()
            if run['state'] in ('planned', 'staging'):
                out['stage'] = L.stage(run, a.max_batches)
                run = L.get_run(run['run_id'])
                if run['state'] != 'staged':
                    out['status'] = L.status(run['run_id'])['run']
                    print(json.dumps(out, indent=2, default=str))
                    return 0
            if run['state'] == 'staged':
                out['verify_stage'] = L.verify_stage(run); run = L.get_run(run['run_id'])
            if run['state'] == 'verified':
                out['sizes_before_activation'] = L.sizes()
                out['activate'] = L.activate(run, a.mode, a.lock_timeout, a.prefix_check)
            if not a.skip_finalize:
                out['finalize'] = L.finalize()
            if a.verify_rollups:
                out['verify_rollups'] = L.verify_rollups()
            out['elapsed_seconds_this_invocation'] = round(time.monotonic() - t0, 3)
            out['sizes'] = L.sizes()
            out['python_peak_rss_bytes'] = rss_bytes()
            out['status'] = L.status(run['run_id'], exact=True)
            out['result_file'] = write_result(f'load-{run["run_id"]}', out)
        print(json.dumps(out, indent=2, default=str))
        if a.cmd == 'verify-rollups' and not out['passed']:
            return 1
        return 0
    except Refused as e:
        log(f'REFUSED: {e}'); return EXIT_REFUSED
    except Conflict as e:
        log(f'CONFLICT: {e}'); return EXIT_CONFLICT
    except InjectedFailure as e:
        log(f'INJECTED FAILURE: {e} (open transaction rolled back)'); return EXIT_INJECTED
    except KeyboardInterrupt:
        log('stopped; committed checkpoints are durable, re-run to resume'); return EXIT_STOPPED
    finally:
        if L is not None:
            try:
                L.conn.close()
            except Exception:
                pass


if __name__ == '__main__':
    sys.exit(main())
