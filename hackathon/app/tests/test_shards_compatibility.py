import unittest
from types import SimpleNamespace
from contextlib import contextmanager
from unittest.mock import patch
import psycopg
from axapi import db, engine

class ShardCompatibility(unittest.TestCase):
    def status(self, error=None):
        shard=SimpleNamespace(name='default',host='localhost')
        class Connection:
            n=0
            def execute(self, *args):
                self.n+=1
                if self.n==3 and error: raise error
                return self
            def fetchall(self):
                if self.n==1: return [{'status':'ACTIVE','verified_at':None,'age_s':None}]
                return [{'tenant_id':1,'orders':7,'seed_orders':5}]
            def fetchone(self): return {'n':0}
        @contextmanager
        def monitor(_): yield Connection()
        with patch.object(db,'probe',return_value={'available':True}), patch.object(db,'monitor',monitor), patch.object(db,'DIRECTORY',{}):
            return engine.shard_status(shard)

    def test_installed_helper_returns_real_counts(self):
        out=self.status(); self.assertEqual(out['orders'],7); self.assertTrue(out['metadata_ok'])
    def test_missing_helper_is_configuration_error(self):
        out=self.status(psycopg.errors.UndefinedFunction())
        self.assertTrue(out['available']); self.assertFalse(out['metadata_ok']); self.assertIn('missing',out['configuration_error'])
    def test_execute_denied_is_configuration_error(self):
        out=self.status(psycopg.errors.InsufficientPrivilege())
        self.assertTrue(out['available']); self.assertIn('permissions',out['configuration_error'])
    def test_other_sql_error_never_succeeds(self):
        self.assertFalse(self.status(psycopg.errors.UndefinedColumn())['metadata_ok'])
    def overview(self, rows):
        with patch.dict(db.SHARDS,{str(i):object() for i in range(len(rows))},clear=True), patch.object(engine,'shard_status',side_effect=rows):
            return engine.shards_overview()
    def test_single_healthy_configured_shard(self):
        o=self.overview([dict(shard='default',available=True,metadata_ok=True,orders=7)])
        self.assertTrue(o['complete']); self.assertEqual(len(o['shards']),1); self.assertEqual(o['total_orders'],7)
    def test_global_totals(self):
        o=self.overview([dict(shard='a',available=True,orders=7),dict(shard='b',available=True,orders=5)])
        self.assertEqual(o['total_orders'],12)
    def test_unreachable_shard_partial_total(self):
        o=self.overview([dict(shard='a',available=True,orders=7),dict(shard='b',available=False)])
        self.assertIsNone(o['total_orders']); self.assertEqual(o['partial_total_orders'],7); self.assertEqual(o['missing_shards'],['b'])
    def test_metadata_error_not_network_partition(self):
        o=self.overview([dict(shard='a',available=True,metadata_ok=False)])
        self.assertFalse(o['complete']); self.assertEqual(o['missing_shards'],[]); self.assertEqual(o['metadata_error_shards'],['a']); self.assertIsNone(o['total_orders'])

    def test_endpoint_returns_partial_diagnostic_without_500(self):
        from fastapi.testclient import TestClient
        from axapi import main, config
        body={'complete':False,'total_orders':None,'partial_total_orders':0,'missing_shards':[],
              'metadata_error_shards':['default'],'shards':[]}
        with patch.object(config,'AUTH_DISABLED',True), patch.object(engine,'shards_overview',return_value=body):
            r=TestClient(main.app).get('/api/shards')
        self.assertEqual(r.status_code,200); self.assertEqual(r.json(),body)
