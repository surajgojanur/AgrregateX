import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from acceptance import verdict, STREAMS


class AcceptanceTests(unittest.TestCase):
    def test_missing_is_not_pass(self):
        self.assertEqual(set(verdict({})['requirements'].values()), {'NOT TESTED'})
    def test_booleans_cannot_verify_functional_requirements(self):
        r=verdict({'functional':{f'FR-{i}':[True] for i in range(1,8)}})
        self.assertTrue(all(r['requirements'][f'FR-{i}']=='FAILED' for i in range(1,8)))
    def test_fast_incomplete_or_invalid_samples_fail(self):
        for value in (1,200,float('nan'),float('inf'),True,-1,'1'):
            self.assertEqual(verdict({'http_ms':[value]})['requirements']['G-1'],'FAILED')
    def test_representative_or_fabricated_flags_never_qualify(self):
        for e in ({'orders':10000000,'populated_tenants':100,'official_dataset_verified':True}, {'source':'live','functional':{'FR-1':[True]}}):
            self.assertFalse(verdict(e)['official_pass'])
    def test_old_growth_pair_cannot_establish_matched_runs(self):
        self.assertEqual(verdict({'growth_pairs':[{'ms_1m':1,'ms_10m':1}]})['requirements']['G-5'],'FAILED')
    def test_flat_oracle_does_not_prove_three_tables(self):
        self.assertEqual(verdict({'oracle_mismatches':[0,0,0]})['requirements']['G-4'],'FAILED')
    def test_g3_reports_throughput_and_latency_separately(self):
        p={'pair_id':'p','baseline_ms':1,'dashboard_ms':1.05,'baseline_tps':100,'dashboard_tps':70}
        r=verdict({'safety_pairs':[p]})
        self.assertAlmostEqual(r['safety_metrics'][0]['latency_slowdown_pct'],5)
        self.assertAlmostEqual(r['safety_metrics'][0]['throughput_regression_pct'],30)
        self.assertEqual(r['requirements']['G-3'],'FAILED')
    def test_live_artifact_and_exact_oracle_coverage(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d,'raw.json').write_text('real-run-fixture-for-validator-unit-test')
            artifact={'path':'raw.json','sha256':hashlib.sha256(Path(d,'raw.json').read_bytes()).hexdigest()}
            run={'source':'live','artifact':'a','orders':10000000,'populated_tenants':100,'execution':'measured','dataset_kind':'organizer',**{k:'fixture' for k in ('hardware','image_digest','git_sha','workload','config_sha256','dataset_sha256')}}
            rows=[{'name':t,'missing_in_st':0,'extra_in_st':0} for t in STREAMS]
            e={'artifacts':{'a':artifact},'runs':{'r':run},'shards':['a'],'oracle_runs':[{'source':'live','artifact':'a','run_id':'r','shard':'a','quiesced':True,'tables':rows}]}
            self.assertEqual(verdict(e,d)['requirements']['G-4'],'VERIFIED')
            self.assertFalse(verdict(e,d)['official_pass'])
            rows.pop()
            self.assertEqual(verdict(e,d)['requirements']['G-4'],'FAILED')
            artifact['sha256']='wrong'
            self.assertEqual(verdict(e,d)['requirements']['G-4'],'FAILED')
    def test_cli_unqualified_exit_one_is_intentional(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d,'evidence.json');p.write_text('{}')
            r=subprocess.run([sys.executable,str(Path(__file__).with_name('acceptance.py')),str(p)],capture_output=True,text=True)
            self.assertEqual(r.returncode,1);self.assertFalse(json.loads(r.stdout)['official_pass']);self.assertEqual(r.stderr,'')


class CoverageTests(unittest.TestCase):
    """Synthetic validator fixtures only; none is real benchmark evidence."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.raw=self.root/'fixture.json';self.raw.write_text('synthetic validator fixture')
        self.record={'source':'live','artifact':'fixture','run_id':'large'}
        run={**self.record,'orders':10000000,'populated_tenants':100,'execution':'measured','dataset_kind':'organizer',**{k:'fixture' for k in ('hardware','image_digest','git_sha','workload','config_sha256','dataset_sha256')}}
        self.e={'artifacts':{'fixture':{'path':'fixture.json','sha256':hashlib.sha256(self.raw.read_bytes()).hexdigest()}},'runs':{'large':run,'small':{**run,'orders':1000000,'populated_tenants':10}}}
    def report(self):return verdict(self.e,self.root)
    def test_latency_requires_each_scenario_and_200_samples(self):
        from acceptance import SCENARIOS
        self.e['latency_cases']=[{**self.record,'scenario':s,'http_ms':[1]*200,'errors':0,'timeouts':0} for s in SCENARIOS]
        self.assertEqual(self.report()['requirements']['G-1'],'VERIFIED')
        self.e['latency_cases'][0]['http_ms'].pop()
        self.assertEqual(self.report()['requirements']['G-1'],'FAILED')
        self.e['latency_cases'].pop()
        self.assertEqual(self.report()['requirements']['G-1'],'FAILED')
    def test_latency_rejects_representative_dataset(self):
        from acceptance import SCENARIOS
        self.e['latency_cases']=[{**self.record,'scenario':s,'http_ms':[1]*200,'errors':0,'timeouts':0} for s in SCENARIOS]
        self.e['runs']['large']['dataset_kind']='representative'
        self.assertEqual(self.report()['requirements']['G-1'],'FAILED')
    def test_freshness_needs_all_mutations_under_writes(self):
        self.e['freshness_cases']=[{**self.record,'mutation':m,'seconds':[1]*20,'errors':0,'timeouts':0,'method':'commit_to_visible_exact_values','sustained_writes':True} for m in ('insert','update','cancel','delete','historical')]
        self.assertEqual(self.report()['requirements']['G-2'],'VERIFIED')
        self.e['freshness_cases'][0]['sustained_writes']=False
        self.assertEqual(self.report()['requirements']['G-2'],'FAILED')
    def test_growth_recomputes_from_matched_full_scale_samples(self):
        from acceptance import SCENARIOS
        self.e['growth_pairs']=[{**self.record,'scenario':s,'run_1m':'small','run_10m':'large','samples_1m':[1]*200,'samples_10m':[1.5]*200,'errors':0,'timeouts':0,'measurement':'http_p95_nearest_rank'} for s in SCENARIOS]
        self.assertEqual(self.report()['requirements']['G-5'],'VERIFIED')
        self.assertFalse(self.report()['official_pass'])
        self.e['runs']['small']['hardware']='another host'
        self.assertEqual(self.report()['requirements']['G-5'],'FAILED')
        self.e['runs']['small']['hardware']='fixture';self.e['runs']['small']['orders']=10000
        self.assertEqual(self.report()['requirements']['G-5'],'FAILED')
    def test_functional_boolean_objects_cannot_verify(self):
        from acceptance import CASES
        self.e['functional']={'FR-1':[{**self.record,'case':c,'execution':'real_sql_http','expected':True,'actual':True,'comparison':'independent_sql_or_security_assertion'} for c in CASES['FR-1']]}
        self.assertEqual(self.report()['requirements']['FR-1'],'FAILED')
    def test_safety_duplicate_pairs_cannot_verify(self):
        p={**self.record,'pair_id':'same','baseline_ms':1,'dashboard_ms':1,'baseline_tps':100,'dashboard_tps':100,'matched_workload':True,'errors':0,'timeouts':0}
        self.e['safety_pairs']=[p]*5
        self.assertEqual(self.report()['requirements']['G-3'],'FAILED')

    def test_malformed_evidence_fails_without_false_success(self):
        for value in ([], {'functional':'bad'}, {'artifacts':[], 'oracle_runs':[True]}):
            self.assertFalse(verdict(value)['official_pass'])
