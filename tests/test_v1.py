import base64
import unittest
from test_core import StocktakeTests as _Base

class V1Tests(unittest.TestCase):
    setUp=_Base.setUp
    tearDown=_Base.tearDown
    change=_Base.change
    record=_Base.record
    def profile(self):return dict(encoding='cp932',header=True,quantity_mode='absolute',specification='架空仕様でのテスト',columns=[dict(name='商品番号',source='code'),dict(name='数量',source='quantity')])
    def finalize(self):
        self.change('receive',[self.record()]);self.change('complete',{'location':'A'});self.change('finalize')
    def test_import_artifact_fixed_and_versioned(self):
        self.finalize();self.change('export_import',self.profile());artifact=self.s['import_artifact']
        self.assertEqual(base64.b64decode(artifact['data']).decode('cp932'),'商品番号,数量\r\n0001,8\r\n')
        self.change('export_import',self.profile());self.assertEqual(artifact,self.s['import_artifact'])
        self.assertEqual(self.s['state'],'exported_import')
        with self.assertRaises(ValueError):self.change('reopen',{'reason':'x'})
    def test_unfinalized_export_rejected(self):
        with self.assertRaises(ValueError):self.change('export_import',self.profile())
    def test_profile_changes_after_export_rejected(self):
        self.finalize();self.change('export_import',self.profile());changed=self.profile();changed['quantity_mode']='delta'
        with self.assertRaises(ValueError):self.change('export_import',changed)
    def test_failed_render_not_marked_exported(self):
        self.finalize();bad=self.profile();bad['quantity_mode']='unknown'
        with self.assertRaises(ValueError):self.change('export_import',bad)
        self.assertEqual(self.store.load(self.s['id'])['state'],'finalized')
del _Base
