# 共通データ交換契約

両機種とPCが共有する論理仕様の置き場。機種固有API・文字コード・物理転送方式は機種側に置く。

現在のschema=1は[既存論理契約](../docs/handheld/preparation.md#論理転送形式試作schema1)と[PC交換手順](../docs/handheld/pc-exchange.md)を参照する。実装は `inventory/handheld.py`、`inventory/exchange.py`、架空データによる検証は `tests/test_handheld.py`、`tests/test_exchange.py` にある。

- 配布: 棚卸ID、元CSVハッシュ、世代、商品、棚位置、distribution_id。
- 実績: 配布版と棚卸ID、端末/担当者/商品/棚位置/実数/訂正元を持つ記録、batch_id。
- 受領: batch_id、distribution_id、受領した記録ID一覧。
- 同一IDの再送で数量を増やさない。未入力とゼロを区別し、訂正と端末間競合を保持する。

現行ハッシュはPython側の正規化JSONによる。別言語で接続する際は同じバイト列を生成する共通テストを追加する。BT-600がこのJSONを直接扱えるとは未確認。必要ならPC側の機種別変換でこの論理契約へ接続する。

契約変更時は版互換性、両機種への影響、再送中の旧版を検証する。サンプルには架空データのみを使用する。
