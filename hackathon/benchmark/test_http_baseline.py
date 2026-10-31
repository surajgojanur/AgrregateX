import io
import json
import unittest
import urllib.error
import tempfile
import hashlib
from pathlib import Path
from unittest.mock import Mock

from acceptance import SCENARIOS, verdict
from http_baseline import metadata, percentile, sample, scenarios, statistics, target
from read_only_compare import reconciliation_ok
from acceptance import STREAMS
from evidence_report import report


class Response(io.BytesIO):
    status = 200


class BaselineTests(unittest.TestCase):
    def test_matrix_reuses_acceptance(self):
        rows = list(scenarios([10, 5, 1], '2026-09-01T00:00:00Z'))
        self.assertEqual({r['scenario'] for r in rows}, SCENARIOS)
        self.assertEqual(len(rows), 48)

    def test_percentiles(self):
        self.assertEqual(percentile(list(range(1, 201)), .95), 190)
        self.assertEqual(percentile([7], .99), 7)
        self.assertIsNone(percentile([], .95))
        self.assertIsNone(statistics([], 1)['p50_ms'])

    def test_target(self):
        self.assertEqual(target('http://127.0.0.1:8094'), 'http://127.0.0.1:8094')
        for url in ['http://example.com:80', 'http://127.0.0.1:80/a', 'http://user@127.0.0.1:80',
                    'http://localhost:80', 'https://127.0.0.1:80', 'http://127.0.0.1']:
            with self.assertRaises(ValueError):
                target(url)

    def test_bad_responses_and_wrong_tenant(self):
        case = dict(scenario='summary/min/1d', tenant=1, family='summary', path='/x')
        for payload in [b'bad', b'null', b'{}', b'{"tenant_id":2,"summary":{}}',
                        b'{"tenant_id":1,"summary":{},"partial_total":true}']:
            row = sample(Mock(open=Mock(return_value=Response(payload))), 'http://127.0.0.1:1', case, 1)
            self.assertFalse(row['ok'])
        row = sample(Mock(open=Mock(return_value=Response(json.dumps({'tenant_id': 1, 'summary': {}}).encode()))),
                     'http://127.0.0.1:1', case, 1)
        self.assertTrue(row['ok'])

    def test_http_errors_timeout(self):
        case = dict(scenario='summary/min/1d', tenant=1, family='summary', path='/x')
        for status in [401, 403, 429, 503]:
            row = sample(Mock(open=Mock(side_effect=urllib.error.HTTPError('x', status, '', {}, None))),
                         'http://127.0.0.1:1', case, 1)
            self.assertFalse(row['ok'])
            self.assertEqual(row['status'], status)
        row = sample(Mock(open=Mock(side_effect=TimeoutError())), 'http://127.0.0.1:1', case, 1)
        self.assertTrue(row['timeout'])
        self.assertEqual(statistics([row], 1)['errors'], 1)

    def test_smoke_cannot_qualify(self):
        self.assertFalse(verdict({'http_ms': [1] * 200, 'official_pass': True})['official_pass'])

    def test_metadata_fails_closed(self):
        for record in [None, {}, {'official_pass': True}, {'orders': 10000000}]:
            with self.assertRaises(ValueError):
                metadata(record, 'http://127.0.0.1:8094')

    def test_oracle_missing_duplicate_and_drift(self):
        rows = [dict(stream_table=t, missing_in_st=0, extra_in_st=0) for t in STREAMS]
        self.assertTrue(reconciliation_ok(rows))
        self.assertFalse(reconciliation_ok(rows[:2]))
        self.assertFalse(reconciliation_ok([rows[0]] * 3))
        rows[0]['extra_in_st'] = 1
        self.assertFalse(reconciliation_ok(rows))
        self.assertFalse(reconciliation_ok([{'count': 0}] * 3))

    def test_report_missing_checksum_and_no_false_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(FileNotFoundError):
                report(root)
            (root / 'http').mkdir()
            (root / 'sql-corrected').mkdir()
            (root / 'http/http.json').write_text(json.dumps({'samples': [{}], 'summary': {}}))
            sql = {'comparisons': [{}], 'failed': 0, 'source_orders': 1002,
                   'reconciliation': [{'stream_table': t, 'missing_in_st': 0, 'extra_in_st': 0} for t in STREAMS],
                   'sql_sha256': 'wrong'}
            (root / 'sql-corrected/executed.sql').write_text('SELECT 1;')
            path = root / 'sql-corrected/comparison.json'
            path.write_text(json.dumps(sql))
            with self.assertRaises(ValueError):
                report(root)
            sql['sql_sha256'] = hashlib.sha256(b'SELECT 1;').hexdigest()
            path.write_text(json.dumps(sql))
            result = report(root)
            self.assertFalse(result['official_pass'])
            self.assertEqual(result['goals']['G4'], 'INCOMPLETE')


if __name__ == '__main__':
    unittest.main()
