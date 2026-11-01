"""Offline structural validation for the observed i3Handy v7 TSV format."""
import argparse
from pathlib import Path
from .validation import text

INDEX_HEADER=['検品開始キー','検品終了キー','納品書総頁数','モード']
KENPIN_HEADER=['検品開始キー','外部伝票番号','案件識別子','IDR（個体識別）フラグ','重量後決めフラグ','サイズ後決めフラグ','輸送種','熨斗印字枚数','熨斗テンプレートID','送り状フラグ','商品コード','ALTSKU1','ALTSKU2','ALTSKU3','DESCR','ｹｰｽ結束','ｲﾝﾅｰ結束','検品数']


def encode_tsv(header, rows):
    all_rows=[header,*rows]
    for row in all_rows:
        if len(row)!=len(header):raise ValueError('列数が不正です')
        for value in row:text(value,'TSV値',512,empty=True)
    return '\r\n'.join('\t'.join(row) for row in all_rows).encode('cp932',errors='strict')


def decode_tsv(raw, header):
    if raw.startswith(b'\xef\xbb\xbf'):raise ValueError('この観測形式はBOMなしCP932です')
    lines=raw.decode('cp932',errors='strict').splitlines()
    rows=[line.split('\t') for line in lines]
    if not rows or rows[0]!=header:raise ValueError('ヘッダーが観測形式と一致しません')
    if len(rows)<2 or any(len(row)!=len(header) for row in rows):raise ValueError('明細または列数が不正です')
    return rows[1:]


def validate_pair(index_raw, kenpin_raw):
    index=decode_tsv(index_raw,INDEX_HEADER);kenpin=decode_tsv(kenpin_raw,KENPIN_HEADER)
    keys=[row[0] for row in index]
    if len(set(keys))!=len(keys) or any(not key for key in keys):raise ValueError('開始キーが空または重複しています')
    if any(r[0]!=r[1] or r[2:]!=['1','2'] for r in index):raise ValueError('観測したINDEX方式ではありません')
    if set(keys)!={r[0] for r in kenpin}:raise ValueError('INDEXと明細の開始キーが一致しません')
    if any(r[0]!=r[1] or not r[10] or not r[17].isascii() or not r[17].isdigit() for r in kenpin):raise ValueError('明細のキー・商品コード・予定数が不正です')
    return dict(index_records=len(index),kenpin_records=len(kenpin),index_columns=4,kenpin_columns=18,encoding='cp932',delimiter='tab')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('index');parser.add_argument('kenpin');args=parser.parse_args()
    print(validate_pair(Path(args.index).read_bytes(),Path(args.kenpin).read_bytes()))
