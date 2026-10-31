# 出荷資材 棚卸補助システム

売りexのCSVとキーエンス BT-W250を連携する棚卸システム。仮CSVで検証できるPC用ローカル試作を実装済み。売りex・BT-W250との実機連携は未実装。

## 開発を再開する

1. このリポジトリを取得し、最新の共有ブランチを確認する。
2. [共通作業ルール](AGENTS.md)を読む。
3. [進捗・引継ぎ](docs/status.md)と[基本設計](docs/design.md)を読む。
4. [プロジェクトskill](.agents/skills/inventory-development/SKILL.md)を読む。

会話履歴や特定端末の設定を正本にしない。設計・判断・進捗・skillはGitで共有する。別端末への共有にはコミットとGitHubへのpushが必要で、ローカル保存だけでは共有されない。

## 構成

```text
AGENTS.md                                 共通の開発ルール
docs/design.md                            基本設計と確認待ち事項
docs/status.md                            現在地と次の作業
docs/skills.md                            skillの共有・導入方針
.agents/skills/                            全5件の共有プロジェクトskill
```

実データCSV、資格情報、端末固有設定はコミットしない。将来のテスト用CSVには架空データを使う。

## 試作を動かす

Python 3.12以上で `python -m inventory.server` を実行する。外部パッケージのインストールは不要。

[操作・テスト・制約](docs/prototype.md) / [CSV・実機確認票](docs/integration-checklist.md)
