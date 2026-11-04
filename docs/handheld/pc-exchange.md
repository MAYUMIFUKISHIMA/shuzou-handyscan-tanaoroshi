# 専用アプリ用PCファイル交換（SDK非依存）

Python 3.12以上、外部Pythonパッケージ不要。実行場所はリポジトリルート。これはPCで使えるローカル交換コマンドで、実機向けアプリやFTPクライアントではない。現場のGakken MST/RESへファイルを置かない。SDK・中継機器の利用条件が確定するまでは専用のローカル検証ディレクトリを使う。

## PC側の操作

既存PC画面でCSV取り込みを行い、棚卸IDを確認する。DBの実際の保存先を指定する。以下のIDは実際の値へ置き換える。出力先ディレクトリはあらかじめ作成する。

```sh
python -m inventory.exchange --db data/prototype.sqlite3 distribute --session 棚卸ID --output data/exchange/distribution.json
python -m inventory.exchange --db data/prototype.sqlite3 receive --input data/exchange/batch.json --receipt data/exchange/receipt.json --actor 回収担当
python -m inventory.exchange --db data/prototype.sqlite3 report --session 棚卸ID --output data/exchange/report-001.json
```

`distribute` は棚卸ID・元CSVハッシュ・配布世代・商品・棚位置を含む配布JSONを出力する。`receive` は端末実績を既存PCの棚卸DBへ反映し、記録ID一覧付きの受領JSONを発行する。`report` は棚位置ごとの未入力（missing）・入力済み（counted）・競合（conflict）、最新実数、差異、端末/担当者付き採用記録、全計数履歴、未登録保留を出力する。競合を合算せず数量はnull、未入力はnull、明示ゼロは文字列0になる。レポートは確認用で、売りex取り込み用CSVではない。

PC回収結果は既存PC画面でも確認できる。画面を再読み込みし、未棚卸・競合・保留を解決してから区画完了・確定・CSV出力へ進む。正式な売りex反映照合は既存設計どおり別工程。

## 模擬端末との接続例

端末側SDKアダプターが完成するまで、ホスト模擬端末を次の共通関数で接続できる。端末DBはPC DBとは別ファイルにする。担当者・端末ID・配布版を途中で変更しない。

```python
from inventory.exchange import read_json, export_terminal_batch, import_receipt
from inventory.handheld import TerminalSimulator

package = read_json('data/exchange/distribution.json')
terminal = TerminalSimulator('data/terminal.sqlite3', package, 'SIM-01')
try:
    terminal.scan('000001')  # 商品選択だけ。コードは配布対象から選ぶ
    terminal.count('000001', '0', 'A', '計数担当')
    export_terminal_batch(terminal, 'data/exchange/batch.json')
    # 別途PC側receiveコマンドを実行してreceipt.jsonが発行された後:
    import_receipt(terminal, 'data/exchange/batch.json', 'data/exchange/receipt.json')
finally:
    terminal.close()
```

コード例の受領処理はPCのreceive実行後に行う。単独で一括実行して受領ファイルがない場合はエラーとなり、未受領の記録を保持する。実機用Pythonではなく、共通交換処理の利用例である。

## 中断・再送・既存ファイル

- UTF-8 JSON（入力はBOM許容）、最大4MB。入力途中のJSON、重複キー、トップレベル配列を拒否する。ハッシュだけでなく既存PCモデルで商品/区画/数量/訂正元/配布版を全件検証し、一括保存する。
- 出力は同一ディレクトリの一時ファイルへ書き、flush/fsync後にハードリンクで完成ファイルを公開する。既存ファイルを上書きしない。同内容の既存JSONは再試行成功、異内容ならエラー。シンボリックリンクの出力先は拒否する。
- ハードリンク非対応ファイルシステムでは出力が失敗する。ローカル対応ディスクを使う。ネットワーク共有/FTPの原子的公開・電源断耐性をこの実装で保証しない。将来の実転送は別の検証が必要。
- PCのDB保存と受領応答は同じDBトランザクションで保持する。受領JSONの出力だけが失敗した場合、PCには受領済みデータが残る。入力は消さず、**同じ入力ファイル・回収担当者**でreceiveを再実行して受領を再発行する。担当者変更は再送内容変更として拒否される。
- 端末の受領確認は保存済みバッチと受領JSONが一致する場合のみ実施する。ファイルの移動/削除やFTP送信成功は受領確認の代わりにならない。受領後も履歴は残す。
- 次のバッチ、更新後のレポートには新しい出力名を使う。古いbatch/receipt/reportを上書きしない。入力/受領/レポートは業務データとして扱い、Gitへ入れない。

## 検証

```sh
python -m unittest discover -s tests -p test_exchange.py -v
```

CLIによる対象出力→回収→確認レポート、0/12/8/7の履歴と差異、未入力との区別、同一回収の重複排除、受領出力失敗→PC DB再起動→再発行、不正バッチの全件ロールバック、途中ファイル/重複キー/サイズ超過拒否、異なる出力の保護、複数端末の競合を検証する。実機・中継機器・売りexへの通信は実行しない。


## 競合の確認と理由付き解決

PC画面の結果フィルターで「未棚卸」と「競合」を別々に選べる。競合した商品・区画を選び、候補の数量と端末を確認し、現物の実数を入力する。「記録する」→候補置換の確認→再計数/確認理由の入力で解決する。空の理由や取消では保存しない。元の候補は履歴に残り、解決理由・担当者・日時・訂正元IDを作業履歴へ記録する。自己申告担当者であり認証や管理者権限を追加したものではない。

CLIからも確認レポートのrevisionと候補IDを使って解決できる。`resolution.json` は次の形で用意する（値はレポートから転記）。

```json
{
  "session_id": "棚卸ID",
  "revision": 2,
  "code": "000001",
  "location": "A",
  "quantity": "7",
  "supersedes": ["候補記録ID1", "候補記録ID2"],
  "reason": "現物を再計数して7を確認"
}
```

```sh
python -m inventory.exchange --db data/prototype.sqlite3 resolve-conflict --input data/exchange/resolution.json --actor 確認担当 --request-id resolve-001
```

操作IDは操作ごとに新規の一意文字列を使い、結果不明の再試行では同じ入力・担当者・操作IDを維持する。データ版や候補IDが変わった場合は拒否し、再レポートを確認してから新しい操作を作る。同一操作IDの内容変更は拒否する。競合していない区画の処理や確定後の変更はこの操作では行わない。解決結果はreportまたは画面再読み込みで確認する。レポートには解決監査履歴も含まれる。
