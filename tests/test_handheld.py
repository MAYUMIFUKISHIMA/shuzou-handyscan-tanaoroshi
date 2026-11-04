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

    def test_scan_never_counts_zero_and_excess_are_explicit(self):
        for _ in range(3):self.terminal.scan('0001')
        self.assertIsNone(self.terminal.inspect('0001','A')['quantity'])
        with self.assertRaises(ValueError):self.terminal.batch()
        for invalid in ('', '-1', None):
            with self.assertRaises(ValueError):self.terminal.count('0001',invalid,'A','test')
        self.terminal.count('0001','0','A','test')
        self.assertEqual(self.terminal.inspect('0001','A')['quantity'],'0')
        self.terminal.scan('0001')
        self.assertEqual(len(self.terminal.inspect('0001','A')['history']),1)
        self.terminal.count('0001','12','A','test')
        self.terminal.close();self.terminal=TerminalSimulator(self.root/'terminal.db',self.package,'sim')
        view=self.terminal.inspect('0001','A')
        self.assertEqual(view['quantity'],'12');self.assertEqual([r['quantity'] for r in view['history']],['0','12'])
        receive_batch(self.pc,self.terminal.batch(),'test')
        self.assertEqual(self.pc.summary(self.pc.load(self.s['id']))[0]['count'],'12')

    def test_correction_during_lost_receipt_keeps_frozen_batch(self):
        first=self.terminal.count('0001','8','A','test');batch=self.terminal.batch()
        receipt=receive_batch(self.pc,batch,'test')
        correction=self.terminal.count('0001','0','A','test')
        self.terminal.close();self.terminal=TerminalSimulator(self.root/'terminal.db',self.package,'sim')
        self.assertEqual(self.terminal.batch(),batch)
        self.assertEqual(receive_batch(self.pc,self.terminal.batch(),'test'),receipt)
        self.terminal.acknowledge(batch,receipt)
        next_batch=self.terminal.batch()
        self.assertEqual(next_batch['records'],[correction])
        self.assertEqual(correction['supersedes'],[first['id']])
        # A delayed duplicate receipt must not clear the newer batch.
        self.terminal.acknowledge(batch,receipt)
        self.assertEqual(self.terminal.batch(),next_batch)
        self.terminal.acknowledge(next_batch,receive_batch(self.pc,next_batch,'test'))
        with self.assertRaises(ValueError):self.terminal.batch()
        self.assertEqual(len(self.pc.load(self.s['id'])['records']),2)
        self.assertEqual(self.pc.summary(self.pc.load(self.s['id']))[0]['count'],'0')
        self.assertEqual(len(self.terminal.inspect('0001','A')['history']),2)

    def test_forged_batch_cannot_mark_records_received(self):
        self.terminal.count('0001','8','A','test');batch=self.terminal.batch()
        forged=copy.deepcopy(batch);forged['session_id']='another'
        receipt=dict(batch_id=forged['batch_id'],distribution_id=forged['distribution_id'],record_ids=[r['id'] for r in forged['records']])
        with self.assertRaises(ValueError):self.terminal.acknowledge(forged,receipt)
        self.assertEqual(self.terminal.batch(),batch)

    def test_failed_acknowledgment_rolls_back_all_flags(self):
        self.terminal.count('0001','8','A','test');self.terminal.count('0001','12','A','test')
        batch=self.terminal.batch();receipt=receive_batch(self.pc,batch,'test')
        self.terminal.db.execute("CREATE TRIGGER fail_ack BEFORE UPDATE ON queue WHEN NEW.id = '%s' BEGIN SELECT RAISE(ABORT, 'disk failure'); END" % batch['records'][1]['id'])
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):self.terminal.acknowledge(batch,receipt)
        self.assertEqual(self.terminal.db.execute('SELECT SUM(received) FROM queue').fetchone()[0],0)
        self.assertEqual(self.terminal.batch(),batch)
        self.terminal.db.execute('DROP TRIGGER fail_ack')
        self.terminal.acknowledge(batch,receipt)
        with self.assertRaises(ValueError):self.terminal.batch()

    def test_minimum_v1_counts_correction_restart_and_recovery(self):
        for value in ('0','8','12','8','7'):
            self.terminal.scan('0001')
            self.terminal.count('0001',value,'A','test')
        self.terminal.close();self.terminal=TerminalSimulator(self.root/'terminal.db',self.package,'sim')
        view=self.terminal.inspect('0001','A')
        self.assertEqual(view['quantity'],'7')
        self.assertEqual([r['quantity'] for r in view['history']],['0','8','12','8','7'])
        batch=self.terminal.batch()
        self.terminal.acknowledge(batch,receive_batch(self.pc,batch,'test'))
        summary=self.pc.summary(self.pc.load(self.s['id']))[0]
        self.assertEqual(summary['count'],'7');self.assertEqual(summary['difference'],'-3')
        self.assertEqual(len(self.pc.load(self.s['id'])['records']),5)

    def test_two_terminals_same_location_remain_a_conflict(self):
        other=TerminalSimulator(self.root/'other.db',self.package,'other')
        try:
            self.terminal.count('0001','8','A','test');other.count('0001','12','A','test')
            receive_batch(self.pc,self.terminal.batch(),'test');receive_batch(self.pc,other.batch(),'test')
            session=self.pc.load(self.s['id'])
            self.assertIsNone(self.pc.summary(session)[0]['count'])
            self.assertEqual([r['quantity'] for r in session['records']],['8','12'])
            with self.assertRaises(ValueError):self.pc.change(session['id'],session['revision'],'complete','test',{'location':'A'})
        finally:other.close()

    def test_failed_count_keeps_previous_saved_value_and_history(self):
        import sqlite3
        self.terminal.count('0001','8','A','test')
        self.terminal.db.execute("CREATE TRIGGER fail_save BEFORE INSERT ON queue BEGIN SELECT RAISE(ABORT, 'disk full'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.terminal.count('0001','7','A','test')
        self.assertEqual(self.terminal.inspect('0001','A')['quantity'],'8')
        self.assertEqual(len(self.terminal.inspect('0001','A')['history']),1)
        self.terminal.db.execute('DROP TRIGGER fail_save')
        self.terminal.count('0001','7','A','test')
        self.assertEqual(self.terminal.inspect('0001','A')['quantity'],'7')
