import unittest

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


if __name__ == "__main__":
    unittest.main()
