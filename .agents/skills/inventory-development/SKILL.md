---
name: inventory-development
description: 売りexのCSVとBT-W250を連携する出荷資材棚卸システムの設計・実装・検証・引継ぎを行う。
---

# 棚卸システム開発

## 開始

リポジトリルートのAGENTS.md、docs/status.md、docs/design.mdを読む。現在のGit状態を確認し、既存変更を保護する。既存チェックアウトを使い、依頼なしにworktreeを作らない。

## 作業別skill

CSVは `../csv-integration/SKILL.md`、棚卸処理は `../stocktake-domain/SKILL.md`、端末は `../handy-terminal-development/SKILL.md`、検証は `../inventory-testing/SKILL.md` を必要に応じて読む。全skillの一覧と依存条件はdocs/skills.mdを参照する。

## 実装と設計

1. 基本設計のERPNext・Odoo・InvenTree参照と採用方針を確認する。類似機能を一から独自設計する前に、対応する既存実装を調べる。
2. CSV変換・棚卸ロジック・端末転送を分離する。売りexの在庫を正本とする。
3. 商品番号の先頭ゼロ、未棚卸とゼロの区別、訂正履歴、再送の重複排除、端末間競合を保持する。
4. 未確認のCSV仕様や端末能力を決めつけない。仮データの前提を明記する。
5. 外部コードを流用する場合は参照版とライセンスを確認する。

## 検証と引継ぎ

変更に該当するdocs/design.mdの受入条件を検証する。実機未検証・CSVサンプル待ちなどの制約を残す。設計変更は設計書、進捗と次の作業はdocs/status.md、skill追加はdocs/skills.mdに反映する。最終報告でローカル保存、コミット、push、実機検証を区別する。
