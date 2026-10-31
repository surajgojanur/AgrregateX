import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

import smoke
from smoke import routes, validate_base_url


class SmokeSafetyTests(unittest.TestCase):
    def test_loopback_base_url_is_accepted(self):
        self.assertEqual(validate_base_url("http://127.0.0.1:8093"), "http://127.0.0.1:8093")

    def test_non_loopback_or_remote_base_is_rejected(self):
        for url in ("http://192.168.1.8:8093", "https://127.0.0.1:8093", "http://example.com:8093"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_base_url(url)

    def test_url_credentials_and_paths_are_rejected(self):
        for url in ("http://user:password@127.0.0.1:8093", "http://127.0.0.1:8093/other"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_base_url(url)

    def test_allowlist_is_bounded_get_only_routes(self):
        paths = routes(1)
        self.assertLessEqual(len(paths), 12)
        self.assertTrue(all(path.startswith("/api/") for path in paths))
        self.assertFalse(any("live-write" in path or "rebuild" in path for path in paths))
        self.assertFalse(any("POST" in path for path in paths))

    def test_invalid_tenant_is_rejected(self):
        for tenant in (0, -1, 999, 10000):
            with self.subTest(tenant=tenant), self.assertRaises(ValueError):
                routes(tenant)



class LocalSmokeResponseTests(unittest.TestCase):
    """A fake localhost server tests redirects and bad 200 responses without external traffic."""

    def probe(self, code, payload=b"", location=None):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(self.server.response_code)
                if self.server.redirect_location:
                    self.send_header("Location", self.server.redirect_location)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(self.server.response_payload)

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        server.response_code = code
        server.response_payload = payload
        server.redirect_location = location
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.object(smoke, "routes", return_value=("/api/health",)):
                rows, passed = smoke.run(f"http://127.0.0.1:{server.server_port}", 1)
            return rows, passed
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_redirect_to_remote_is_blocked(self):
        rows, passed = self.probe(302, location="https://example.com/secret")
        self.assertFalse(passed)
        self.assertEqual(rows[0]["status"], 302)
        self.assertEqual(rows[0]["error"], "redirect_blocked")

    def test_html_200_does_not_pass(self):
        rows, passed = self.probe(200, b"<html>not JSON</html>")
        self.assertFalse(passed)
        self.assertEqual(rows[0]["error"], "invalid_json_or_schema")

    def test_incomplete_json_200_does_not_pass(self):
        rows, passed = self.probe(200, b'{"status":"ok"}')
        self.assertFalse(passed)
        self.assertFalse(rows[0]["response_schema_valid"])

    def test_valid_health_json_200_passes(self):
        rows, passed = self.probe(200, json.dumps({"status": "ok", "shards": {"default": "ok"}}).encode())
        self.assertTrue(passed)
        self.assertTrue(rows[0]["response_schema_valid"])


if __name__ == "__main__":
    unittest.main()
