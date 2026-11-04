# 出荷資材 棚卸補助システム

売りexのCSVとキーエンスのハンディを連携する棚卸システム。BT-W250とBT-600を機種別に開発する。仮CSVで検証できるPC用ローカル試作を実装済み。売りex・BT-W250との実機連携は未実装。

## 開発を再開する

1. このリポジトリを取得し、最新の共有ブランチを確認する。
2. [共通作業ルール](AGENTS.md)を読む。
3. [進捗・引継ぎ](docs/status.md)と[基本設計](docs/design.md)を読む。
4. [プロジェクトskill](.agents/skills/inventory-development/SKILL.md)を読む。

会話履歴や特定端末の設定を正本にしない。設計・判断・進捗・skillはGitで共有する。別端末への共有にはコミットとGitHubへのpushが必要で、ローカル保存だけでは共有されない。

[クラウド・ISJ055の連携と引継ぎ](docs/collaboration.md)

## 構成

```text
inventory/            共通処理・PCアプリ・ホスト模擬端末
tests/                共通処理・PC側の試験
contracts/            共通データ交換契約
devices/bt-w250/      BT-W250用アプリ（未実装）
devices/bt-600/       BT-600用アプリ（調査段階）
docs/common/         共通設計・PC資料の入口
docs/bt-w250/        BT-W250の開発情報
docs/bt-600/         BT-600の開発情報
```

実データCSV、資格情報、端末固有設定はコミットしない。将来のテスト用CSVには架空データを使う。

## 試作を動かす

Python 3.12以上で `python -m inventory.server` を実行する。外部パッケージのインストールは不要。

[操作・テスト・制約](docs/prototype.md) / [CSV・実機確認票](docs/integration-checklist.md)

[現場PC1台の起動・復元・ブラウザーテスト](docs/single-pc-operations.md)

## 完成を判断する基準

[完成判定表](docs/release-acceptance.md)のD01〜D07を確定し、A01〜A08をすべて満たして現場受入責任者が承認した時点をシステム完成とする。現在はPC試作段階。自動テスト成功やGitHubへのpushだけでは完成扱いにしない。

[棚卸専用ハンディV1の要件・現在地](docs/handheld/dedicated-v1.md)（専用アプリ開発方針、SDK確認待ち）

[BT-W250の開発準備・PC模擬試験](docs/handheld/preparation.md)（SDKと端末向けビルドは確認待ち）

[ハンディ棚卸V1の目標手順と確認待ち](docs/v1-pc-pilot.md)

[専用ハンディ用PCファイル交換](docs/handheld/pc-exchange.md)：対象配布・実績回収・受領発行・未入力/競合レポート（ローカル実装、実機FTP未接続）。
