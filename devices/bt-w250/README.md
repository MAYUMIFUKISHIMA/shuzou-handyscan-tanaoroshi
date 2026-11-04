# BT-W250用アプリ

端末用ソース・プロジェクト・機種別試験の置き場。現時点では実機用ソース/実行ファイルは未実装。

Windows Embedded Compact 7、C#/.NET Compact Framework 3.5を第一候補とする。VS2008 Professional SP1とBT-WHD1実機SDKが必要。詳細は[機種資料](../../docs/bt-w250/README.md)。SDK・DLL・ライセンス・業務データはGitへ登録しない。

画面、スキャナー、キー、保存、通信アダプターをここに実装する。共通PC実装は `inventory/`、交換契約は `contracts/`。BT-600向けコードをこのフォルダーへ混在させない。ビルド/配布/更新/戻し手順、試験結果、対象版は機種単位で記録する。
