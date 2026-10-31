"""Host-side signed-cookie session. Never writes cookies or passwords to evidence."""
import http.cookiejar
import json
import urllib.request
from urllib.parse import urlsplit


def login(base, password):
    url = urlsplit(base)
    if url.scheme != 'http' or url.hostname not in ('127.0.0.1', 'localhost') or url.username or url.password or url.path not in ('', '/') or url.query or url.fragment:
        raise ValueError('Disposable benchmark API must be on loopback HTTP')
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise ValueError('Benchmark session redirects are forbidden')
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), NoRedirect())
    payload = json.dumps({'email': 'admin@demo.local', 'password': password}).encode()
    with opener.open(urllib.request.Request(base.rstrip('/')+'/api/auth/login', data=payload,
                      headers={'Content-Type': 'application/json'}), timeout=5) as response:
        if response.status != 200 or not any(c.name == 'ax_session' for c in jar):
            raise ValueError('Operator signed-cookie login failed')
    return opener
