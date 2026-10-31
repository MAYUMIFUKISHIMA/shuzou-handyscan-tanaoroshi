"""Explicit CSV output adapter; no built-in vendor-format assumptions."""
import csv
import io
from .validation import text


def render_import_csv(rows, profile):
    if not isinstance(profile,dict) or set(profile)!={'encoding','header','quantity_mode','columns','specification'}:
        raise ValueError('出力設定の項目が不正です')
    text(profile['specification'],'形式の確認根拠',512)
    if profile['encoding'] not in ('utf-8','utf-8-sig','cp932') or type(profile['header']) is not bool or profile['quantity_mode'] not in ('absolute','delta'):
        raise ValueError('文字コード・ヘッダー・数量の意味を明示してください')
    columns=profile['columns']
    if not isinstance(columns,list) or not 2<=len(columns)<=100:
        raise ValueError('出力列は2〜100列です')
    names=[];sources=[]
    for column in columns:
        if not isinstance(column,dict) or set(column) not in ({'name','source'},{'name','constant'}):
            raise ValueError('列の値はsourceまたはconstantで指定してください')
        text(column['name'],'列名');names.append(column['name'])
        if 'source' in column:
            if column['source'] not in ('code','name','quantity'):raise ValueError('未対応の出力項目です')
            sources.append(column['source'])
        else:text(column['constant'],'固定値',512,empty=True)
    if len(set(names))!=len(names) or sources.count('code')!=1 or sources.count('quantity')!=1:
        raise ValueError('列名の重複を避け、商品番号と数量を各1列指定してください')
    if not rows:raise ValueError('確定結果がありません')
    out=io.StringIO(newline='');writer=csv.writer(out,lineterminator='\r\n')
    if profile['header']:writer.writerow(names)
    for row in rows:
        if row.get('count') is None or row.get('difference') is None:raise ValueError('未確定の数量があります')
        values=dict(code=row['code'],name=row['name'],quantity=row['count'] if profile['quantity_mode']=='absolute' else row['difference'])
        writer.writerow([values[col['source']] if 'source'in col else col['constant'] for col in columns])
    return out.getvalue().encode(profile['encoding'],errors='strict')
