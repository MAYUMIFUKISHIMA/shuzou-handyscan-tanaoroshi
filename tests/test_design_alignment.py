import hashlib
import unittest
from unittest.mock import patch
from test_core import StocktakeTests as _Base, CSV
from inventory.core import capacity_plan

class DesignAlignmentTests(unittest.TestCase):
    setUp = _Base.setUp
    tearDown = _Base.tearDown
    change = _Base.change
    record = _Base.record
    def test_capacity_rejects_incompleteable_work(self):
        for count,locations,reserve in [(5000,['A','B','C','D'],None),(5000,list('ABCDEFGHIJKLMNOPQRST'),1),(1,['A'],0),(1,['A'],True)]:
            with self.subTest(count=count,locations=locations),self.assertRaises(ValueError):capacity_plan(count,locations,reserve)
        self.assertEqual(capacity_plan(5000,['A','B'],10000)['required'],20000)
    def test_capacity_failure_is_atomic(self):
        with patch('inventory.core.MAX_RECORDS',1):
            with self.assertRaises(ValueError):self.store.create(CSV,['A'],'t')
        self.assertEqual(len(self.store.list()),1)
    def test_review_is_invalidated_by_correction(self):
        self.change('receive',[self.record()]);self.change('complete',{'location':'A'})
        self.assertEqual(self.s['state'],'reviewing')
        self.change('receive',[self.record('r2','7',supersedes=['r1'])])
        self.assertEqual(self.s['state'],'counting');self.assertEqual(self.s['completed'],[])
    def test_version_and_confirmation_export(self):
        self.change('receive',[self.record()]);self.change('complete',{'location':'A'});self.change('finalize')
        self.assertEqual(self.s['result_version'],1);self.assertEqual(self.s['finalized_by'],'tester')
        self.change('reopen',{'reason':'再確認'});self.change('complete',{'location':'A'});self.change('finalize');self.change('export')
        self.assertEqual(self.s['result_version'],2);self.assertEqual(self.s['previous_results'][0]['version'],1)
        manifest=self.s['export_manifest'];self.assertEqual(manifest['kind'],'confirmation_only')
        self.assertEqual(self.s['export_hash'],hashlib.sha256(self.s['csv'].encode('utf-8-sig')).hexdigest())
        self.change('export');self.assertEqual(manifest,self.s['export_manifest'])
    def test_legacy_database_remains_usable(self):
        for key in ['capacity','created_at','result_version','mode']:
            self.s.pop(key,None)
        import json
        with self.store.db:self.store.db.execute('UPDATE sessions SET body=? WHERE id=?',(json.dumps(self.s),self.s['id']))
        self.change('receive',[self.record()]);self.change('complete',{'location':'A'});self.change('finalize')
        self.assertEqual(self.s['result_version'],1)

del _Base
