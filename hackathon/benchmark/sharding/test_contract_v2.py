import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
import session
from preflight import check
from verify_oracles import clean, TABLES

class ContractV2(unittest.TestCase):
    def test_fault_requires_approval_without_running_docker(self):
        import os
        env=os.environ.copy();env.pop('AX_FAULT_APPROVED',None)
        r=subprocess.run(['bash',str(Path(__file__).with_name('partition.sh'))],env=env,capture_output=True,text=True)
        self.assertEqual(r.returncode,2);self.assertIn('BLOCKED',r.stderr)
    def test_resource_or_ownership_gate_fails(self):
        for rows,ram,swap in [([],4000,0),([{'Labels':{}}],4000,0),([],1000,5000)]:
            with self.assertRaises(ValueError):check(rows,ram,swap,10*1024**3)
    def test_oracle_missing_duplicate_nonzero_rejected(self):
        good=[{'stream_table':t,'missing_in_st':0,'extra_in_st':0} for t in TABLES]
        self.assertTrue(clean(good));self.assertFalse(clean([]));self.assertFalse(clean(good[:2]));self.assertFalse(clean([good[0]]*3))
        good[0]['extra_in_st']=1;self.assertFalse(clean(good))
    def test_cookie_login_from_host(self):
        from http.server import BaseHTTPRequestHandler, HTTPServer
        import threading
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.server.payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                self.send_response(200);self.send_header('Set-Cookie','ax_session=test-signed-cookie; HttpOnly; Path=/');self.end_headers()
            def do_GET(self):
                self.server.cookie=self.headers.get('Cookie');self.send_response(200);self.end_headers()
            def log_message(self,*args):pass
        server=HTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            base=f'http://127.0.0.1:{server.server_port}'
            opener=session.login(base,'fixture-password')
            with opener.open(base+'/api/tenants/2/summary',timeout=2):pass
            self.assertIn('ax_session=',server.cookie);self.assertEqual(server.payload['email'],'admin@demo.local')
        finally:server.shutdown();server.server_close();thread.join()
    def test_login_rejects_nonlocal_target(self):
        with self.assertRaises(ValueError):session.login('http://example.com','fixture')
