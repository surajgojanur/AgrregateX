"""Loader recovery/correctness tests (Phase 01A).

Requires a DISPOSABLE PostgreSQL cluster; never point this at the Phase 00
database. Each test creates and drops its own database from database/schema.sql.

  LOADER_TEST_ADMIN_DSN=postgresql://agrregatex_owner@127.0.0.1:25499/postgres \
    python3 -m unittest discover -s generator/tests -v
"""
import json, os, signal, subprocess, sys, threading, time, unittest, uuid
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo

ROOT = Path(__file__).resolve().parents[2]
LOADER = ROOT / 'generator' / 'loader.py'
ADMIN = os.environ.get('LOADER_TEST_ADMIN_DSN')

# Phase 00 generator/load.py (commit 84aab53) batch SQL, verbatim incl. its category fix.
LEGACY = """SELECT CASE WHEN h<400000 THEN 1 WHEN h<600000 THEN 2 ELSE 3+(h%{T2})::int END tenant_id,-i id,
 1+(hc%100)::int customer_id,1+(hp%32)::int product_id,1+((hp%32)::int%8) category_id,
 '2026-08-03 00:00:00+00'::timestamptz+make_interval(secs=>(ht%7776000)::double precision) ordered_at,
 CASE WHEN hs%10=0 THEN 'cancelled' WHEN hs%10<5 THEN 'shipped' ELSE 'placed' END status,
 1+(hq%4)::int quantity,100+(hm%50000) unit_price_cents
 FROM (SELECT i,(hashtextextended(i::text,42)&9223372036854775807)%1000000 h,
 (hashtextextended(i::text,43)&9223372036854775807) hc,(hashtextextended(i::text,44)&9223372036854775807) hp,
 (hashtextextended(i::text,45)&9223372036854775807) ht,(hashtextextended(i::text,46)&9223372036854775807) hs,
 (hashtextextended(i::text,47)&9223372036854775807) hq,(hashtextextended(i::text,48)&9223372036854775807) hm
 FROM generate_series(1::bigint,{N}::bigint) i) x"""


@unittest.skipUnless(ADMIN, 'set LOADER_TEST_ADMIN_DSN to a disposable cluster')
class LoaderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with psycopg.connect(ADMIN, autocommit=True) as c:
            if not c.execute("SELECT 1 FROM pg_roles WHERE rolname='agrregatex_api'").fetchone():
                c.execute("CREATE ROLE agrregatex_api LOGIN NOSUPERUSER NOBYPASSRLS")

    def setUp(self):
        self.db = 'loader_t_' + uuid.uuid4().hex[:10]
        with psycopg.connect(ADMIN, autocommit=True) as c:
            c.execute(f'CREATE DATABASE {self.db}')
        self.dsn = self.dsn_for(self.db)
        with psycopg.connect(self.dsn, autocommit=True) as c:
            c.execute((ROOT / 'database' / 'schema.sql').read_text())

    def tearDown(self):
        with psycopg.connect(ADMIN, autocommit=True) as c:
            c.execute(f'DROP DATABASE IF EXISTS {self.db} WITH (FORCE)')
        for extra in getattr(self, 'extra_dbs', []):
            with psycopg.connect(ADMIN, autocommit=True) as c:
                c.execute(f'DROP DATABASE IF EXISTS {extra} WITH (FORCE)')

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def dsn_for(db):
        d = conninfo_to_dict(ADMIN); d['dbname'] = db
        return make_conninfo(**d)

    def new_db(self):
        name = 'loader_t_' + uuid.uuid4().hex[:10]
        self.extra_dbs = getattr(self, 'extra_dbs', []) + [name]
        with psycopg.connect(ADMIN, autocommit=True) as c:
            c.execute(f'CREATE DATABASE {name}')
        dsn = self.dsn_for(name)
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute((ROOT / 'database' / 'schema.sql').read_text())
        return dsn

    def cli(self, *args, dsn=None, env=None, check=None):
        e = dict(os.environ); e.pop(LOADER_GATE, None)
        e.update(ADMIN_DATABASE_URL=dsn or self.dsn, **(env or {}))
        p = subprocess.run([sys.executable, str(LOADER), *map(str, args)], env=e, capture_output=True, text=True,
                           timeout=600)
        if check is not None:
            self.assertEqual(p.returncode, check, p.stderr[-2000:])
        return p

    def popen(self, *args, dsn=None):
        e = dict(os.environ, ADMIN_DATABASE_URL=dsn or self.dsn)
        return subprocess.Popen([sys.executable, str(LOADER), *map(str, args)], env=e,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def q(self, sql, dsn=None, params=None):
        with psycopg.connect(dsn or self.dsn, autocommit=True) as c:
            c.execute("SET TIME ZONE 'UTC'")
            cur = c.execute(sql, params)
            return cur.fetchall() if cur.description else []

    def v(self, sql, dsn=None, params=None):
        return self.q(sql, dsn, params)[0][0]

    def state(self, dsn=None):
        return self.v('SELECT state FROM loader.runs ORDER BY updated_at DESC LIMIT 1', dsn)

    def batches(self, dsn=None):
        return self.v('SELECT count(*) FROM loader.batches b JOIN loader.runs r USING (run_id) '
                      "WHERE r.state<>'aborted'", dsn)

    def source_fingerprint(self, dsn=None):
        return self.v("SELECT count(*)::text||':'||sum(hashtextextended(concat_ws('|',tenant_id,id,customer_id,product_id,"
                      "category_id,extract(epoch FROM ordered_at),status,quantity,unit_price_cents),0)::numeric)::text "
                      'FROM orders', dsn)

    def assert_reconciled(self, dsn=None):
        p = self.cli('verify-rollups', dsn=dsn)
        self.assertEqual(p.returncode, 0, p.stdout[-2000:] + p.stderr[-2000:])

    def trigger_enabled(self, dsn=None):
        return self.v("SELECT tgenabled FROM pg_trigger WHERE tgname='rollups' AND tgrelid='orders'::regclass", dsn) == 'O'

    LOAD = ('load', '--rows', 9000, '--tenants', 7, '--batch-size', 1000)

    # ------------------------------------------------------------------ tests
    def test_full_load_reconciles_and_is_isolated_from_api(self):
        self.cli(*self.LOAD, check=0)
        self.assertEqual(self.state(), 'active')
        self.assertEqual(self.v('SELECT count(*) FROM orders'), 9000)
        self.assertEqual(self.v('SELECT count(DISTINCT id) FROM orders'), 9000)
        self.assertEqual(self.v('SELECT count(*) FROM loader.stage_orders'), 0, 'stage freed at activation')
        self.assertTrue(self.trigger_enabled())
        self.assert_reconciled()
        top = self.q('SELECT tenant_id,count(*) FROM orders GROUP BY 1 ORDER BY 2 DESC')
        self.assertEqual(len(top), 7)
        self.assertEqual(top[0][0], 1)
        self.assertGreater(top[0][1], 0.35 * 9000)  # uneven: hot tenant ~40%
        with psycopg.connect(self.dsn, autocommit=True) as c:
            c.execute('SET ROLE agrregatex_api')
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                c.execute('SELECT count(*) FROM loader.stage_orders')

    def test_manifest_interface(self):
        self.cli('init', check=0)
        self.assertEqual(self.q('SELECT manifest FROM loader.dataset_manifest'), [])
        self.cli('manifest', check=2)
        self.cli(*self.LOAD, '--verify-rollups', check=0)
        self.q("UPDATE orders SET quantity=2 WHERE id=-5")
        m = json.loads(self.cli('manifest', check=0).stdout)
        self.assertEqual(m, {**self.v('SELECT manifest FROM loader.dataset_manifest'), 'result_file': m['result_file']})
        self.assertEqual((m['manifest_version'], m['generator'], m['generator_version'], m['seed']),
                         (1, 'representative-v1', 1, 42))
        self.assertEqual(m['official_dataset_compatibility'], 'NOT VERIFIED')
        self.assertEqual((m['target_rows'], m['source_rows'], m['bulk_rows'], m['api_rows'], m['tenant_count']),
                         (9000, 9000, 9000, 0, 7))
        self.assertEqual(sum(t['rows'] for t in m['tenant_distribution']), 9000)
        self.assertTrue(m['stage_verification']['passed'])
        self.assertTrue(m['load_completed_at'])
        self.assertIn('loader_commit', m)
        val = m['validations']['verify-rollups']
        self.assertTrue(val['passed'] and val['after_load'])
        self.assertEqual(val['mismatches'], {'daily_product': 0, 'hourly_category': 0})

    def test_rows_match_phase00_legacy_formula(self):
        self.cli('init', check=0)
        self.cli('plan', '--rows', 5000, '--tenants', 10, '--batch-size', 700, check=0)
        self.cli('stage', check=0)
        cols = 'tenant_id,id,customer_id,product_id,category_id,ordered_at,status,quantity,unit_price_cents'
        stage = (f'SELECT tenant_id,-ordinal id,customer_id,product_id,category_id,ordered_at,status,quantity,'
                 f'unit_price_cents FROM loader.stage_orders')
        legacy = f'SELECT {cols} FROM ({LEGACY.format(T2=8, N=5000)}) l'
        self.assertEqual(self.v(f'SELECT count(*) FROM (({stage}) EXCEPT ALL ({legacy})) d'), 0)
        self.assertEqual(self.v(f'SELECT count(*) FROM (({legacy}) EXCEPT ALL ({stage})) d'), 0)

    def test_interrupt_crash_resume_is_deterministic(self):
        ref = self.new_db()
        self.cli(*self.LOAD, dsn=ref, check=0)
        # clean injected failure after 3 committed batches
        self.cli(*self.LOAD, '--fail-after-batches', 3, check=75)
        self.assertEqual(self.batches(), 3)
        self.assertEqual(self.v('SELECT count(*) FROM loader.stage_orders'), 3000)
        self.assertEqual(self.v('SELECT count(*) FROM orders'), 0, 'nothing exposed before activation')
        # hard process exit inside the 2nd batch transaction of this invocation
        p = self.cli(*self.LOAD, '--crash-in-batch', 2)
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(self.batches(), 4)
        self.assertEqual(self.v('SELECT count(*) FROM loader.stage_orders'), 4000, 'open batch rolled back')
        self.assertEqual(self.v('SELECT sum(n) FROM loader.delta_daily'), 4000, 'deltas match checkpoints')
        self.cli(*self.LOAD, check=0)
        self.assertEqual(self.source_fingerprint(), self.source_fingerprint(ref))
        self.assertEqual(self.v('SELECT count(DISTINCT id) FROM orders'), 9000)
        for t in ('daily_product', 'hourly_category'):
            a = self.q(f'SELECT * FROM {t} ORDER BY 1,2,3,4' + (',5' if t == 'daily_product' else ''))
            b = self.q(f'SELECT * FROM {t} ORDER BY 1,2,3,4' + (',5' if t == 'daily_product' else ''), ref)
            self.assertEqual(a, b, t)
        self.assert_reconciled()

    def test_sigkill_mid_staging_then_resume(self):
        args = ('load', '--rows', 300000, '--tenants', 20, '--batch-size', 5000)
        p = self.popen(*args)
        deadline = time.time() + 60
        while time.time() < deadline:
            if self.v("SELECT count(*) FROM pg_tables WHERE schemaname='loader' AND tablename='batches'") and \
               self.v('SELECT count(*) FROM loader.batches') >= 3:
                break
            time.sleep(0.05)
        p.send_signal(signal.SIGKILL); p.communicate()
        killed_at = self.batches()
        self.assertGreaterEqual(killed_at, 3)
        self.assertEqual(self.state(), 'staging')
        self.assertEqual(self.v('SELECT count(*) FROM loader.stage_orders'), killed_at * 5000)
        self.assertEqual(self.v('SELECT count(*) FROM orders'), 0)
        self.cli(*args, check=0)
        self.assertEqual(self.v('SELECT count(*) FROM orders'), 300000)
        self.assertEqual(self.v('SELECT count(DISTINCT id) FROM orders'), 300000)
        self.assert_reconciled()

    def test_sigterm_stops_at_batch_boundary(self):
        args = ('load', '--rows', 300000, '--tenants', 20, '--batch-size', 5000)
        p = self.popen(*args)
        deadline = time.time() + 60
        while time.time() < deadline:
            if self.v("SELECT count(*) FROM pg_tables WHERE schemaname='loader' AND tablename='batches'") and \
               self.v('SELECT count(*) FROM loader.batches') >= 2:
                break
            time.sleep(0.05)
        p.send_signal(signal.SIGTERM)
        p.communicate(timeout=60); self.assertEqual(p.returncode, 130)
        n = self.batches()
        self.assertEqual(self.v('SELECT count(*) FROM loader.stage_orders'), n * 5000)
        self.cli(*args, check=0)
        self.assertEqual(self.v('SELECT count(*) FROM orders'), 300000)
        self.assert_reconciled()

    def test_retries_are_idempotent_and_tampering_is_rejected(self):
        self.cli(*self.LOAD, check=0)
        before = self.source_fingerprint()
        rollups = self.q('SELECT sum(n),sum(cents) FROM daily_product')
        p = self.cli(*self.LOAD, check=0)          # re-run after activation: no-op
        self.assertNotIn('"activate"', p.stdout)
        self.cli('stage', check=0)                  # stage after activation: refused per batch? none remaining
        self.cli('activate', check=0)               # already active -> no-op
        self.assertEqual(self.source_fingerprint(), before)
        self.assertEqual(self.q('SELECT sum(n),sum(cents) FROM daily_product'), rollups)
        self.assertEqual(self.v('SELECT count(*) FROM loader.batches'), 9)

        # Tampering: a staged row in an uncheckpointed batch range is a conflict.
        db2 = self.new_db()
        self.cli('init', dsn=db2, check=0)
        self.cli('plan', '--rows', 5000, '--tenants', 5, '--batch-size', 1000, dsn=db2, check=0)
        self.cli('stage', '--max-batches', 1, dsn=db2, check=0)
        self.q("INSERT INTO loader.stage_orders VALUES (1500,1,1,1,2,now(),'placed',1,100)", db2)
        self.cli('stage', dsn=db2, check=3)
        self.assertEqual(self.batches(db2), 1)
        self.assertEqual(self.v('SELECT count(*) FROM loader.stage_orders', db2), 1001)
        self.assertEqual(self.v('SELECT sum(n) FROM loader.delta_daily', db2), 1000)
        self.cli('abort', dsn=db2, check=0)
        self.assertEqual(self.v('SELECT count(*) FROM loader.stage_orders', db2), 0)
        self.cli('load', '--rows', 5000, '--tenants', 5, '--batch-size', 1000, dsn=db2, check=0)
        self.assert_reconciled(db2)

    def test_conflicting_spec_and_concurrent_loader_refused(self):
        self.cli('init', check=0)
        self.cli('plan', '--rows', 5000, '--tenants', 5, check=0)
        self.cli('plan', '--rows', 6000, '--tenants', 5, check=2)
        self.assertEqual(self.v('SELECT count(*) FROM loader.runs'), 1)
        with psycopg.connect(self.dsn, autocommit=True) as c:
            c.execute('SELECT pg_advisory_lock(4157204001)')
            p = self.cli('--lock-wait', 1, 'stage', check=2)
            self.assertIn('holds the loader lock', p.stderr)
        self.assertEqual(self.batches(), 0)

    def test_full_scale_is_gated(self):
        self.cli('init', check=0)
        p = self.cli('plan', '--rows', 10_000_000, '--tenants', 100, check=2)
        self.assertIn('gated', p.stderr)
        self.cli('plan', '--rows', 10_000_000, '--tenants', 100, '--allow-full-scale', check=2)
        self.assertEqual(self.v('SELECT count(*) FROM loader.runs'), 0)
        # Phase 00 command-line wrapper routes through the same gate.
        e = dict(os.environ, ADMIN_DATABASE_URL=self.dsn); e.pop(LOADER_GATE, None)
        p = subprocess.run([sys.executable, str(ROOT / 'generator' / 'load.py'), '10000000', '100'], env=e,
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertEqual(self.v('SELECT count(*) FROM orders'), 0)

    def test_failed_activation_rolls_back_completely(self):
        self.cli(*self.LOAD, '--fail-in-activation', check=75)
        self.assertEqual(self.v('SELECT count(*) FROM orders'), 0)
        self.assertEqual(self.v('SELECT count(*) FROM daily_product'), 0)
        self.assertEqual(self.v('SELECT count(*) FROM tenants'), 0)
        self.assertTrue(self.trigger_enabled())
        self.assertEqual(self.state(), 'verified')
        self.assertEqual(self.v('SELECT count(*) FROM loader.stage_orders'), 9000)
        self.cli(*self.LOAD, check=0)
        self.assert_reconciled()

    def test_api_writes_before_activation_and_atomic_visibility_for_readers(self):
        args = ('load', '--rows', 120000, '--tenants', 6, '--batch-size', 20000)
        # Pre-existing tenant data and API-style writes (positive ids, through the trigger).
        self.q("INSERT INTO tenants VALUES (1,'Store 1'),(2,'Store 2');"
               "INSERT INTO products SELECT t,i,1+(i-1)%8,'Product '||i FROM generate_series(1,2) t,generate_series(1,32) i;"
               "INSERT INTO customers SELECT t,i FROM generate_series(1,2) t,generate_series(1,100) i;"
               "INSERT INTO orders(tenant_id,customer_id,product_id,category_id,ordered_at,status,quantity,unit_price_cents) "
               "SELECT 1+i%2,1,1+i%32,1+((i%32)%8),'2026-09-01'::timestamptz+i*interval '37 minutes','placed',2,999 "
               "FROM generate_series(1,500) i")
        self.cli('init', check=0)
        self.cli('plan', *args[1:], check=0)
        self.cli('stage', check=0)
        # Concurrent historical changes while staged data waits.
        self.q("UPDATE orders SET status='cancelled',ordered_at=ordered_at-interval '3 days',version=version+1 WHERE id%5=0;"
               "DELETE FROM orders WHERE id%7=0")
        old = self.q('SELECT (SELECT count(*) FROM orders),(SELECT sum(n) FROM daily_product),(SELECT sum(n) FROM hourly_category)')[0]
        seen, stop = set(), threading.Event()

        def reader():
            with psycopg.connect(self.dsn, autocommit=True) as c:
                while not stop.is_set():
                    seen.add(c.execute('SELECT (SELECT count(*) FROM orders),(SELECT sum(n) FROM daily_product),'
                                       '(SELECT sum(n) FROM hourly_category)').fetchone())
        th = threading.Thread(target=reader); th.start()
        try:
            self.cli('verify-stage', check=0)
            self.cli('activate', check=0)
        finally:
            time.sleep(0.2); stop.set(); th.join()
        new = (old[0] + 120000, old[1] + 120000, old[2] + 120000)
        self.assertEqual(self.q('SELECT (SELECT count(*) FROM orders),(SELECT sum(n) FROM daily_product),'
                                '(SELECT sum(n) FROM hourly_category)')[0], new)
        self.assertTrue(seen <= {old, new}, f'partial state observed: {seen - {old, new}}')
        self.assertIn(old, seen); self.assertIn(new, seen)
        self.assert_reconciled()
        # API writes after activation keep rollups exact (trigger re-enabled).
        self.q("UPDATE orders SET quantity=quantity+1,version=version+1 WHERE id BETWEEN -50 AND -1;"
               "DELETE FROM orders WHERE id BETWEEN -80 AND -60")
        self.assert_reconciled()

    def test_prefix_extension_and_provenance_check(self):
        self.cli('load', '--rows', 4000, '--tenants', 5, '--batch-size', 900, check=0)
        self.cli('load', '--rows', 10000, '--tenants', 9, '--batch-size', 900, '--prefix-rows', 4000,
                 '--prefix-tenants', 5, check=0)
        self.assertEqual(self.v('SELECT count(*) FROM orders'), 10000)
        self.assertEqual(self.v('SELECT count(DISTINCT tenant_id) FROM orders'), 9)
        self.assert_reconciled()
        # A modified prefix row is detected; --prefix-check count accepts it knowingly.
        db2 = self.new_db()
        self.cli('load', '--rows', 4000, '--tenants', 5, dsn=db2, check=0)
        self.q('UPDATE orders SET quantity=quantity+1 WHERE id=-17', db2)
        ext = ('load', '--rows', 6000, '--tenants', 5, '--prefix-rows', 4000, '--prefix-tenants', 5)
        self.cli(*ext, dsn=db2, check=3)
        self.assertEqual(self.v('SELECT count(*) FROM orders', db2), 4000)
        self.cli(*ext, '--prefix-check', 'count', dsn=db2, check=0)
        self.assertEqual(self.v('SELECT count(*) FROM orders', db2), 6000)
        self.assert_reconciled(db2)
        # wrong prefix size is refused
        db3 = self.new_db()
        self.cli('load', '--rows', 3000, '--tenants', 5, dsn=db3, check=0)
        self.cli(*ext, dsn=db3, check=3)

    def test_rebuild_index_mode(self):
        self.cli(*self.LOAD, '--mode', 'rebuild-index', check=0)
        self.assertEqual(self.v("SELECT count(*) FROM pg_indexes WHERE indexname='orders_time'"), 1)
        self.assert_reconciled()

    def test_rebuild_rollups_repairs_drift_and_preserves_security(self):
        self.cli(*self.LOAD, check=0)
        pooled = psycopg.connect(self.dsn, autocommit=True)  # long-lived session, like the API pool
        pooled.execute("UPDATE orders SET quantity=quantity WHERE id=-1")  # warm trigger plan cache
        self.q('UPDATE daily_product SET n=n+1 WHERE ctid=(SELECT min(ctid) FROM daily_product)')
        self.q('DELETE FROM hourly_category WHERE ctid=(SELECT min(ctid) FROM hourly_category)')
        self.assertEqual(self.cli('verify-rollups').returncode, 1)
        p = self.cli('rebuild-rollups', check=0)
        self.assertIn('"drift_rows_repaired": 1', p.stdout)
        self.assert_reconciled()
        for t in ('daily_product', 'hourly_category'):
            self.assertTrue(self.v(f"SELECT relrowsecurity FROM pg_class WHERE oid='{t}'::regclass"))
            self.assertEqual(self.v(f"SELECT count(*) FROM pg_policies WHERE tablename='{t}'"), 1)
            self.assertTrue(self.v(f"SELECT has_table_privilege('agrregatex_api','{t}','SELECT')"))
            self.assertEqual(self.v(f"SELECT count(*) FROM pg_indexes WHERE indexname='{t}_pkey'"), 1)
        # The pre-existing session's cached trigger plan must target the new tables.
        pooled.execute("UPDATE orders SET status='cancelled',version=version+1 WHERE id BETWEEN -30 AND -1")
        pooled.execute('DELETE FROM orders WHERE id BETWEEN -60 AND -40')
        pooled.close()
        self.assert_reconciled()
        # RLS still isolates tenants on the swapped tables.
        with psycopg.connect(self.dsn, autocommit=True) as c:
            c.execute("SET ROLE agrregatex_api"); c.execute("SELECT set_config('app.tenant','3',false)")
            self.assertEqual(c.execute('SELECT count(DISTINCT tenant_id) FROM daily_product').fetchone()[0], 1)


LOADER_GATE = 'AGRREGATEX_LOADER_ALLOW_FULL_SCALE'

if __name__ == '__main__':
    unittest.main()
