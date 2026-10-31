import unittest
from unittest.mock import patch
import urllib.error
import metrics

class FakeResponse:
    status=200
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read(self): return b'ok'

class MetricsTests(unittest.TestCase):
    def test_success_latency_excludes_http_503(self):
        with patch.object(metrics.urllib.request,'urlopen',side_effect=[FakeResponse(),urllib.error.HTTPError('u',503,'bad',{},None)]):
            result=metrics.measure('http://unused',count=2)
        self.assertEqual(result['successes'],1)
        self.assertEqual(len(result['errors']),1)
        self.assertEqual(result['errors'][0]['status'],503)
        self.assertIsNotNone(result['successful_latency_ms_nearest_rank']['p50'])
    def test_timeout_separate_from_errors_and_success(self):
        with patch.object(metrics.urllib.request,'urlopen',side_effect=TimeoutError()):
            result=metrics.measure('http://unused',count=1)
        self.assertEqual(result['timeouts'],1)
        self.assertEqual(result['successes'],0)
        self.assertIsNone(result['successful_latency_ms_nearest_rank']['p95'])
    def test_urlerror_timeout_reason_is_timeout(self):
        with patch.object(metrics.urllib.request,'urlopen',side_effect=urllib.error.URLError(TimeoutError())):
            result=metrics.measure('http://unused',count=1)
        self.assertEqual(result['timeouts'],1)
        self.assertEqual(result['errors'],[])

if __name__=='__main__': unittest.main()
