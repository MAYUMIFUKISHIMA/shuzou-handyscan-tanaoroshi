import copy
import unittest
from inventory.csv_export import render_import_csv

class ExportTests(unittest.TestCase):
    def setUp(self):
        self.rows=[dict(code='0001',name='箱,小',count='8',difference='-2')]
        self.profile=dict(encoding='cp932',header=True,quantity_mode='absolute',columns=[dict(name='番号',source='code'),dict(name='在庫',source='quantity'),dict(name='名称',source='name')],specification='架空仕様: 売りex形式未確認')
    def test_explicit_columns_and_absolute(self):
        self.assertEqual(render_import_csv(self.rows,self.profile).decode('cp932'),'番号,在庫,名称\r\n0001,8,"箱,小"\r\n')
    def test_delta_headerless_constant(self):
        self.profile.update(quantity_mode='delta',header=False);self.profile['columns'].append(dict(name='区分',constant='棚卸'))
        self.assertEqual(render_import_csv(self.rows,self.profile).decode('cp932'),'0001,-2,"箱,小",棚卸\r\n')
    def test_no_silent_replacement(self):
        self.rows[0]['name']='😀'
        with self.assertRaises(UnicodeEncodeError):render_import_csv(self.rows,self.profile)
    def test_missing_confirmation_and_quantity(self):
        for key,value in [('quantity_mode','unknown'),('specification',''),('columns',[])]:
            p=copy.deepcopy(self.profile);p[key]=value
            with self.assertRaises(ValueError):render_import_csv(self.rows,p)
        self.rows[0]['count']=None
        with self.assertRaises(ValueError):render_import_csv(self.rows,self.profile)
