import tempfile
import unittest
from pathlib import Path
from inventory.core import Store, read_csv

CSV='商品番号,名称,数量\n0001,"箱,小",10\n'.encode()

class StocktakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.path=Path(self.tmp.name)/'test.db'; self.store=Store(self.path)
        self.s=self.store.create(CSV,['A'],'tester')
    def tearDown(self):
        self.store.close(); self.tmp.cleanup()
    def change(self,action,payload=None):
        self.s=self.store.change(self.s['id'],self.s['revision'],action,'tester',payload); return self.s
    def record(self,id='r1',qty='8',loc='A',supersedes=None,device='d1'):
        return dict(id=id,device=device,code='0001',location=loc,quantity=qty,operator='tester',supersedes=supersedes or [])
    def test_difference_and_export(self):
        self.change('receive',[self.record()]); self.assertEqual(self.store.summary(self.s)[0]['difference'],'-2')
        self.change('complete',{'location':'A'}); self.change('finalize'); self.change('export'); csv=self.s['csv']
        self.assertIn('0001,"箱,小",10,8,-2',csv); self.change('export'); self.assertEqual(csv,self.s['csv'])
        with self.assertRaises(ValueError):self.change('receive',[self.record('r2')])
    def test_zero_is_not_missing(self):
        self.assertIsNone(self.store.summary(self.s)[0]['count'])
        with self.assertRaises(ValueError):self.change('finalize')
        self.change('receive',[self.record(qty='0')]); self.assertEqual(self.store.summary(self.s)[0]['count'],'0')
    def test_correction_keeps_history_and_reopens_location(self):
        self.change('receive',[self.record()]); self.change('complete',{'location':'A'})
        self.change('receive',[self.record('r2','7',supersedes=['r1'])]); self.assertEqual(len(self.s['records']),2)
        self.assertEqual(self.store.summary(self.s)[0]['count'],'7'); self.assertEqual(self.s['completed'],[])
    def test_locations(self):
        self.s=self.store.create(CSV,['A','B'],'tester'); self.change('receive',[self.record(qty='3'),self.record('r2','5','B')])
        self.assertEqual(self.store.summary(self.s)[0]['count'],'8')
    def test_retry_and_id_collision(self):
        self.change('receive',[self.record()]); self.change('receive',[self.record()]); self.assertEqual(len(self.s['records']),1)
        with self.assertRaises(ValueError):self.change('receive',[self.record(qty='9')])
    def test_conflict_and_resolution(self):
        self.change('receive',[self.record(),self.record('r2','9',device='d2')])
        with self.assertRaises(ValueError):self.change('complete',{'location':'A'})
        self.change('receive',[self.record('r3','7',supersedes=['r1','r2'])]); self.assertEqual(self.store.summary(self.s)[0]['count'],'7')
    def test_atomic_batch(self):
        bad=self.record('r2'); bad['code']='unknown'
        with self.assertRaises(ValueError):self.change('receive',[self.record(),bad])
        self.assertEqual(self.store.load(self.s['id'])['records'],[])
    def test_invalid_quantities(self):
        for qty in ['-1','NaN','Infinity','1e6','','1.1234567']:
            with self.subTest(qty=qty), self.assertRaises(ValueError):self.change('receive',[self.record(qty=qty)])
    def test_stale_revision(self):
        self.change('receive',[self.record()])
        with self.assertRaises(ValueError):self.store.change(self.s['id'],0,'complete','tester',{'location':'A'})
    def test_restart(self):
        self.change('receive',[self.record()]); self.store.close(); self.store=Store(self.path)
        self.assertEqual(self.store.summary(self.store.load(self.s['id']))[0]['count'],'8')
    def test_csv_validation(self):
        self.assertEqual(read_csv(CSV)[0]['code'],'0001')
        cp='番号,品名,在庫\n001,箱,1.25\n'.encode('cp932')
        self.assertEqual(read_csv(cp,'cp932',{'code':'番号','name':'品名','baseline':'在庫'})[0]['baseline'],'1.25')
        for raw in [CSV+b'0001,duplicate,1\n',CSV+b'0002,bad,NaN\n',b'',b'bad\xff']:
            with self.subTest(raw=raw),self.assertRaises((ValueError,UnicodeError)):read_csv(raw)
    def test_failed_import_creates_nothing(self):
        with self.assertRaises(ValueError):self.store.create(CSV+b'0002,bad,no\n',['A'],'tester')
        self.assertEqual(len(self.store.list()),1)
    def test_incomplete_location(self):
        self.s=self.store.create(CSV,['A','B'],'tester'); self.change('receive',[self.record()]); self.change('complete',{'location':'A'})
        with self.assertRaises(ValueError):self.change('finalize')
    def test_stale_correction(self):
        self.change('receive',[self.record()]); self.change('receive',[self.record('r2','7',supersedes=['r1'])])
        with self.assertRaises(ValueError):self.change('receive',[self.record('r3','6',supersedes=['r1'])])
