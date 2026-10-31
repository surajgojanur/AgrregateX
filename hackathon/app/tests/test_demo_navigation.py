import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from axapi import auth, config, monitoring

class DemoNavigation(unittest.TestCase):
    def test_demo_operator_and_secure_negative_paths(self):
        app = FastAPI()
        monitoring.install(app)
        client = TestClient(app)
        with patch.object(monitoring.cache, 'get', return_value={'shards': []}):
            with patch.object(config, 'AUTH_DISABLED', True):
                self.assertEqual(client.get('/api/monitoring').status_code, 200)
            with patch.object(config, 'AUTH_DISABLED', False):
                self.assertEqual(client.get('/api/monitoring').status_code, 401)
                client.cookies.set(auth.COOKIE, auth.issue(auth.User('tenant1@demo.local', 'tenant', 1)))
                self.assertEqual(client.get('/api/monitoring').status_code, 403)
