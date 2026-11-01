"""Generate synthetic test files locally. Never access or overwrite device shares."""
import argparse
import base64
import hashlib
import html
import io
import json
from pathlib import Path
import zipfile
from inventory.gakken_files import INDEX_HEADER,KENPIN_HEADER,encode_tsv,validate_pair


def build(output, labels=False):
    output=Path(output)
    if output.exists():raise FileExistsError('新規フォルダーを指定してください。既存データは上書きしません')
    index=[];kenpin=[];scenarios=[]
    for i,(actual,label) in enumerate([('8','予定10に対し実数8。可能なら7へ訂正'),('12','予定超過12'),('0','実数ゼロ'),(None,'未読取・未棚卸')],1):
        key=f'9900{i}';sku=f'TST0000{i}'
        index.append([key,key,'1','2'])
        row=['']*18;row[0]=row[1]=key;row[2]='TEST';row[10]=row[11]=sku;row[14]=f'TEST ITEM {i}';row[15]=row[16]='1';row[17]='10';kenpin.append(row)
        scenarios.append(dict(start_key=key,code=sku,planned='10',actual=actual,check=label))
    files={'INDEX.TXT':encode_tsv(INDEX_HEADER,index),'KENPIN.TXT':encode_tsv(KENPIN_HEADER,kenpin)}
    validate_pair(files['INDEX.TXT'],files['KENPIN.TXT'])
    label_html='<meta charset="utf-8"><title>試験専用ラベル</title><h1>架空商品・出荷作業に使用しない</h1><p>印刷は100%倍率。コードの左右に余白を残してください。</p>'
    if labels:
        from reportlab.graphics.barcode import createBarcodeDrawing
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        pdf_buffer=io.BytesIO()
        pdf=canvas.Canvas(pdf_buffer,pagesize=A4)
        pdf.setTitle('Synthetic barcode trial - print at actual size')
        for scenario in scenarios:
            label_html+='<section style="page-break-inside:avoid;border:1px solid #aaa;padding:20px;margin:20px"><h2>'+html.escape(scenario['check'])+'</h2>'
            pdf.setFont('Helvetica-Bold',16)
            pdf.drawString(20*mm,275*mm,'TEST ONLY - NOT FOR SHIPPING')
            pdf.setFont('Helvetica',11)
            pdf.drawString(20*mm,263*mm,'Print at actual size (100%). Keep white margins.')
            pdf_y=225*mm
            for name,value in [('開始キー',scenario['start_key']),('商品コード',scenario['code'])]:
                drawing=createBarcodeDrawing('Code128',value=value,barHeight=20*mm,barWidth=0.5*mm,humanReadable=True,quiet=True)
                # Each SVG needs its own document: inline ReportLab SVGs reuse
                # id="clip", clipping longer product codes to the first label.
                svg=drawing.asString('svg')
                encoded=base64.b64encode(svg.encode('utf-8') if isinstance(svg,str) else svg).decode('ascii')
                label_html+='<p>'+name+': '+value+'</p><img alt="'+html.escape(value)+'" style="display:block;width:'+str(drawing.width/mm)+'mm;height:auto" src="data:image/svg+xml;base64,'+encoded+'">'
                pdf.drawString(20*mm,pdf_y+30*mm,('START / END: ' if name=='開始キー' else 'PRODUCT: ')+value)
                drawing.drawOn(pdf,20*mm,pdf_y)
                pdf_y-=80*mm
            label_html+='</section>'
            pdf.showPage()
        pdf.save()
        files['labels.pdf']=pdf_buffer.getvalue()
    else:label_html+='<p>バーコードラベル生成には --labels とReportLabが必要です。</p>'
    files['labels.html']=label_html.encode('utf-8')
    readme='''架空データによる既存アプリ適合試験（棚卸V1完成版ではありません）

このパッケージは静的に検証した観測形式の候補で、実機受理は未検証です。
INDEX.TXT / KENPIN.TXT は既存出荷用データと分離してください。
転送プログラムや自動アップロードは含めていません。

投入前: 出荷作業を止められる担当者と確認し、既存の端末入力・未回収実績と
共有MSTファイルを保全し、元の状態へ戻せることを確認してください。
接続未確認のままマクロの出力・投入・リセットは実行しないでください。
FTPで使う既存経路が復旧し、元ファイルを保護できた後にのみ試します。
端末USBメニューは現場マニュアルに停止注意があり使用しません。

1. まず分離した保存先でファイルを確認。案件識別子TEST、Code128の対応は実機未確認。
2. labels.pdfを実際のサイズ（100%）で印刷し、開始キー99001を読んでTST00001の商品を確認する。
   PDFは1ページ1組（開始・終了キーと商品コード）。labels.htmlも印刷可能。
3. 予定10に合わせず、実数8を入力・保存できるか調べる。可能なら7へ訂正する。
4. 99002/TST00002は実数12、99003/TST00003は実数0を試す。
5. 99004/TST00004は未読取のままにし、ゼロと区別されるか調べる。
6. 予定数量に合わせるまで完了不可・実数入力不可なら、適合不可/保留として止める。
   予定数量を書き換えて「成功」にしない。架空データのリセットをする場合も履歴を先に保全する。
7. 結果を既存のFTP経路で回収し、SKU毎実績と伝票毎実績のコピーを保存する。
8. 件数・ID・予定数・実数・訂正を照合する。実績形式未確定のため回収の自動変換は未実装。
9. 保全した出荷設定・データへ戻す。実際の売りexへの投入には使用しない。

Code128ラベルは各コードを読み取れることの補助。読取設定・キー形式が不適合なら
設定を無断で変更せず結果を記録する。開始キーと商品コードは実在品と無関係の試験値です。
'''
    files['README.txt']=readme.encode('utf-8')
    manifest=dict(purpose='synthetic_compatibility_test_not_production',hardware_verified=False,
                  transfer_included=False,scenarios=scenarios,sha256={name:hashlib.sha256(raw).hexdigest()for name,raw in files.items()})
    files['manifest.json']=json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf-8')
    output.mkdir(parents=True)
    for name,raw in files.items():(output/name).write_bytes(raw)
    archive=output/'test-package.zip'
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
        for name,raw in files.items():z.writestr(name,raw)
    return archive


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--labels',action='store_true');a=p.parse_args();print(build(a.output,a.labels))
