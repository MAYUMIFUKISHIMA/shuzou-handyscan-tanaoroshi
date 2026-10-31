import copy
import tempfile
import unittest
from pathlib import Path
from inventory.core import Store
from inventory.handheld import distribution,TerminalSimulator,receive_batch,digest

class HandheldTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.pc=Store(self.root/'pc.db')
        self.s=self.pc.create('商品番号,名称,数量\n0001,箱,10\n'.encode(),['A'],'test');self.package=distribution(self.s)
        self.terminal=TerminalSimulator(self.root/'terminal.db',self.package,'sim')
    def tearDown(self):self.terminal.close();self.pc.close();self.tmp.cleanup()
    def test_restart_lost_receipt_retry(self):
        r=self.terminal.count('0001','8','A','test');self.terminal.close();self.terminal=TerminalSimulator(self.root/'terminal.db',self.package,'sim')
        b=self.terminal.batch();ack=receive_batch(self.pc,b,'test');self.assertEqual(receive_batch(self.pc,self.terminal.batch(),'test'),ack)
        self.assertEqual(len(self.pc.load(self.s['id'])['records']),1);self.terminal.acknowledge(b,ack)
        with self.assertRaises(ValueError):self.terminal.batch()
    def test_bad_receipt_preserves_unsent(self):
        self.terminal.count('0001','8','A','test');b=self.terminal.batch()
        with self.assertRaises(ValueError):self.terminal.acknowledge(b,{})
        self.assertEqual(b,self.terminal.batch())
    def test_correction_and_zero(self):
        self.terminal.count('0001','8','A','test');self.terminal.count('0001','0','A','test')
        b=self.terminal.batch();receive_batch(self.pc,b,'test');self.assertEqual(self.pc.summary(self.pc.load(self.s['id']))[0]['count'],'0')
    def test_corrupt_and_stale_distribution(self):
        self.terminal.count('0001','8','A','test');b=self.terminal.batch();bad=copy.deepcopy(b);bad['records'][0]['quantity']='9'
        with self.assertRaises(ValueError):receive_batch(self.pc,bad,'test')
        bad=copy.deepcopy(b);bad['distribution_id']='old';bad['batch_id']=digest({k:v for k,v in bad.items() if k!='batch_id'})
        with self.assertRaises(ValueError):receive_batch(self.pc,bad,'test')
        self.assertEqual(self.pc.load(self.s['id'])['records'],[])
    def test_unknown_does_not_save(self):
        with self.assertRaises(ValueError):self.terminal.count('unknown','8','A','test')
        with self.assertRaises(ValueError):self.terminal.batch()
    def test_reject_different_device_storage(self):
        with self.assertRaises(ValueError):TerminalSimulator(self.root/'terminal.db',self.package,'another')
