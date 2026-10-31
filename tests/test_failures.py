import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from inventory.core import Store, read_csv
from inventory.backup import backup
from inventory.validation import request, headers

CSV='商品番号,名称,数量\n001,箱,10\n'.encode()

class FailureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.path=Path(self.tmp.name)/'db';self.store=Store(self.path)
    def tearDown(self):
        self.store.close();self.tmp.cleanup()
    def create(self):return self.store.create(CSV,['A'],'test')
    def test_create_retry_after_response_loss_and_restart(self):
        body={'request_id':'operation1','action':'create'}
        result=self.store.execute_once(body,lambda:{'id':self.create()['id']})
        self.store.close();self.store=Store(self.path)
        self.assertEqual(self.store.execute_once(body,lambda:self.fail('must not execute')),result)
        self.assertEqual(len(self.store.list()),1)
    def test_idempotency_collision(self):
        self.store.execute_once({'request_id':'one'},lambda:{'id':self.create()['id']})
        with self.assertRaises(ValueError):self.store.execute_once({'request_id':'one','different':True},lambda:{})
    def test_receipt_and_data_atomic(self):
        self.store.db.execute("CREATE TRIGGER fail_receipt BEFORE INSERT ON receipts BEGIN SELECT RAISE(ABORT,'simulated write failure'); END")
        with self.assertRaises(sqlite3.Error):self.store.execute_once({'request_id':'one'},lambda:{'id':self.create()['id']})
        self.assertEqual(self.store.list(),[])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM sources').fetchone()[0],0)
    def test_disk_full_transaction(self):
        self.store.db.execute('PRAGMA max_page_count=20')
        raw=('商品番号,名称,数量\n'+''.join(f'{i},'+('箱'*100)+',1\n' for i in range(1000))).encode()
        with self.assertRaises(sqlite3.OperationalError) as exc:self.store.create(raw,['A'],'test')
        self.assertIn('full',str(exc.exception));self.assertEqual(self.store.list(),[])
    def test_database_locked_and_retry(self):
        other=sqlite3.connect(self.path);other.execute('BEGIN IMMEDIATE')
        try:
            with self.assertRaises(sqlite3.OperationalError):self.create()
        finally:other.rollback();other.close()
        self.create();self.assertEqual(len(self.store.list()),1)
    def test_readonly(self):
        self.store.close();self.store.db=sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True)
        with self.assertRaises(sqlite3.OperationalError):self.create()
    def test_corrupt_database(self):
        path=Path(self.tmp.name)/'corrupt';path.write_bytes(b'not sqlite'*200)
        with self.assertRaises(sqlite3.DatabaseError):Store(path)
    def test_backup_restore_and_no_overwrite(self):
        s=self.create();target=Path(self.tmp.name)/'backup';backup(self.path,target)
        with self.assertRaises(FileExistsError):backup(self.path,target)
        restored=Store(target)
        try:self.assertEqual(restored.load(s['id'])['items'][0]['code'],'001')
        finally:restored.close()
    def test_failed_backup_cleans_partial(self):
        target=Path(self.tmp.name)/'backup'
        with patch('inventory.backup.sqlite3.connect',side_effect=PermissionError('denied')):
            with self.assertRaises(PermissionError):backup(self.path,target)
        self.assertFalse(target.exists());self.assertTrue(self.path.exists())
    def test_input_types(self):
        for value in [None,[],1,'x',{'action':[]},{'action':'no'}]:
            with self.subTest(value=value),self.assertRaises(ValueError):request(value)
        for loc in [None,'A',[{}],['A','A'],[' '],['A']*21]:
            with self.subTest(loc=loc),self.assertRaises(ValueError):self.store.create(CSV,loc,'test')
        for columns in [[],{'code':[]},{},'x']:
            with self.subTest(columns=columns),self.assertRaises(ValueError):read_csv(CSV,columns=columns)
    def test_limits(self):
        with self.assertRaises(ValueError):headers(b'a'*1000001,'utf-8-sig')
        with self.assertRaises(ValueError):read_csv(('商品番号,名称,数量\n'+''.join(f'{i},箱,1\n' for i in range(5001))).encode())
        self.assertEqual(len(read_csv(('商品番号,名称,数量\n'+''.join(f'{i},箱,1\n' for i in range(5000))).encode())),5000)
    def test_control_characters_and_unicode_numbers(self):
        for raw in ['商品番号,名称,数量\n001,\x00,1\n','商品番号,名称,数量\n001,箱,１２\n','商品番号,名称,数量\n001,   ,1\n']:
            with self.assertRaises(ValueError):read_csv(raw.encode())
    def test_reopen_preserves_frozen_result(self):
        s=self.create()
        def change(action,payload=None):
            nonlocal s
            s=self.store.change(s['id'],s['revision'],action,'test',payload)
        change('receive',[dict(id='r',device='d',code='001',location='A',quantity='8',operator='t',supersedes=[])])
        change('complete',{'location':'A'});change('finalize');change('reopen',{'reason':'再確認'})
        self.assertEqual(s['previous_results'][0]['result'][0]['count'],'8');self.assertEqual(s['completed'],[])
        change('complete',{'location':'A'});change('finalize');change('export')
        with self.assertRaises(ValueError):change('reopen',{'reason':'訂正'})
    def test_unknown_hold_blocks_finalize_and_resolves(self):
        s=self.create()
        def change(action,payload=None):
            nonlocal s
            s=self.store.change(s['id'],s['revision'],action,'test',payload)
        held=dict(id='h',device='d',code='unknown',location='A',quantity='8',operator='t')
        change('hold',held)
        with self.assertRaises(ValueError):change('finalize')
        record=dict(id='r',device='d',code='001',location='A',quantity='8',operator='t',supersedes=[])
        change('resolve',dict(id='h',reason='現品照合',record=record))
        self.assertEqual(self.store.summary(s)[0]['count'],'8');self.assertEqual(s['held'][0]['status'],'resolve')
    def test_hold_dismissal_audit(self):
        s=self.create();s=self.store.change(s['id'],0,'hold','test',dict(id='h',device='d',code='unknown',location='A',quantity='1',operator='t'))
        s=self.store.change(s['id'],1,'dismiss','test',dict(id='h',reason='誤読'))
        self.assertEqual(s['held'][0]['reason'],'誤読');self.assertEqual(s['records'],[])
    def test_unknown_resolution_rolls_back(self):
        s=self.create();s=self.store.change(s['id'],0,'hold','test',dict(id='h',device='d',code='unknown',location='A',quantity='1',operator='t'))
        with self.assertRaises(ValueError):self.store.change(s['id'],1,'resolve','test',dict(id='h',reason='wrong',record={}))
        self.assertEqual(self.store.load(s['id'])['held'][0]['status'],'open')

    def test_launcher_backup_and_restore(self):
        from inventory.launcher import prepare
        self.create();destination=Path(self.tmp.name)/'external'
        saved=prepare(self.path,destination)
        restored=Store(saved)
        try:self.assertEqual(len(restored.list()),1)
        finally:restored.close()
        with patch('inventory.launcher.backup',side_effect=PermissionError('denied')):
            with self.assertRaises(PermissionError):prepare(self.path,destination)
        self.assertEqual(len(self.store.list()),1)
