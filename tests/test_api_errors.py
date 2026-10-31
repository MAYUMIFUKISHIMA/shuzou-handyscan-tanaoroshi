import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch
from inventory.server import serve

class ApiErrorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.server=serve(Path(self.tmp.name)/'db',0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}/api'
    def tearDown(self):
        self.server.shutdown();self.thread.join();self.server.server_close();self.tmp.cleanup()
    def send(self,body):
        req=urllib.request.Request(self.url,data=body,headers={'Content-Type':'application/json','X-Token':self.server.token})
        try:
            with urllib.request.urlopen(req) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as exc:return exc.code,json.load(exc)
    def test_malformed_requests_do_not_crash(self):
        for body in [b'null',b'[]',b'{',b'{"action":1}',b'{"action":"finalize","revision":true}',b'{"action":"inspect","csv":null}',b'{"action":"inspect","csv":"%%%"}',b'{"action":"inspect","action":"preview","csv":""}',b'{"action":"create","value":NaN}']:
            with self.subTest(body=body):self.assertEqual(self.send(body)[0],400)
        with urllib.request.urlopen(self.url) as response:self.assertEqual(response.status,200)
    def test_storage_errors_are_actionable(self):
        for exc in [sqlite3.OperationalError('database is locked'),sqlite3.DatabaseError('corrupt'),PermissionError('denied')]:
            with self.subTest(error=exc),patch('inventory.server.Store',side_effect=exc):
                try:urllib.request.urlopen(self.url)
                except urllib.error.HTTPError as response:
                    self.assertEqual(response.code,503);self.assertIn('error',json.load(response))
                else:self.fail('expected service error')
    def test_post_storage_error(self):
        with patch('inventory.server.Store',side_effect=sqlite3.OperationalError('disk full')):
            status,result=self.send(b'{"action":"inspect","csv":"YQ=="}')
            self.assertEqual(status,503);self.assertIn('容量',result['error'])
    def test_wrong_host_is_rejected(self):
        req=urllib.request.Request(self.url,headers={'Host':'attacker.example'})
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(req)
        self.assertEqual(error.exception.code,403)
