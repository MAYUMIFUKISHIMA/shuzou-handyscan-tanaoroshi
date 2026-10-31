import base64
import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from inventory.server import serve

class HttpTests(unittest.TestCase):
    def test_workflow_and_request_protection(self):
        with tempfile.TemporaryDirectory() as tmp:
            server=serve(Path(tmp)/'db.sqlite3',0)
            thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
            root=f'http://127.0.0.1:{server.server_port}'
            def get():
                with urllib.request.urlopen(root+'/api') as r:return json.load(r)
            def post(data,token):
                req=urllib.request.Request(root+'/api',data=json.dumps(data).encode(),headers={'Content-Type':'application/json','X-Token':token})
                with urllib.request.urlopen(req) as r:return json.load(r)
            try:
                with urllib.request.urlopen(root) as r:self.assertIn('棚卸ワークスペース',r.read().decode())
                token=get()['token']
                with self.assertRaises(urllib.error.HTTPError) as error:post({},'wrong')
                self.assertEqual(error.exception.code,403)
                raw='商品番号,名称,数量\n001,架空箱,10\n'.encode()
                post(dict(action='create',actor='test',locations=['A'],csv=base64.b64encode(raw).decode()),token)
                s=get()['sessions'][0]
                record=dict(id='r1',device='test',code='001',location='A',quantity='8',operator='test',supersedes=[])
                for action,payload in [('receive',[record]),('complete',{'location':'A'}),('finalize',None),('export',None)]:
                    post(dict(action=action,actor='test',id=s['id'],revision=s['revision'],payload=payload),token)
                    s=get()['sessions'][0]
                self.assertEqual(s['state'],'exported'); self.assertEqual(s['summary'][0]['difference'],'-2')
                self.assertIn('001,架空箱,10,8,-2',s['csv'])
            finally:
                server.shutdown(); thread.join(); server.server_close()
