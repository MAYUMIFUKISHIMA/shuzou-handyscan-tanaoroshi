# 共通設計・PC側資料

- [基本設計](../design.md)
- [進捗・未完了一覧](../status.md)
- [完成判定](../release-acceptance.md)
- [承認済み棚卸要件](../handheld/dedicated-v1.md)
- [交換契約](../../contracts/README.md)
- [PC交換・競合解決](../handheld/pc-exchange.md)
- [PC起動・復旧](../single-pc-operations.md)

共通要件は単一の正本を維持し、機種ごとにコピーしない。既存文書のBT-W250を対象とした記述は当時の対象範囲であり、BT-600の適合確認を代替しない。今後両機種に適用する変更は共通設計に根拠を残す。

アプリのPython実装とPC模擬端末は `inventory/`。機種別実装は `devices/bt-w250/` と `devices/bt-600/`。共通のPC試験は `tests/` に維持する。機種別の変更は対応フォルダーに限定し、共通変更時は両機種への影響を確認する。作業ごとのブランチを使い、恒久的な機種別ブランチで共通コードを二重管理しない。
