# skillの共有

## リポジトリ内skill

| skill | 用途 | 出所・依存条件 |
| --- | --- | --- |
| [inventory-development](../.agents/skills/inventory-development/SKILL.md) | 本プロジェクトの設計・開発・引継ぎ | 本プロジェクト用に作成。外部コードの転用なし。特別なツール依存なし |
| [csv-integration](../.agents/skills/csv-integration/SKILL.md) | 売りexのCSV入出力の仕様確認、変換、検証と往復テストを行う。 | 本プロジェクト作成。外部コード転用なし。実装に応じた実行環境を使用 |
| [stocktake-domain](../.agents/skills/stocktake-domain/SKILL.md) | 棚卸の数量、訂正、競合、再送、確定処理を既存OSSの設計に基づいて開発する。 | 本プロジェクト作成。外部コード転用なし。実装に応じた実行環境を使用 |
| [handy-terminal-development](../.agents/skills/handy-terminal-development/SKILL.md) | BT-W250の公式仕様、開発環境、入力、保存、転送を調査し実機検証する。 | 本プロジェクト作成。外部コード転用なし。実機・公式SDKの提供条件は別途確認 |
| [inventory-testing](../.agents/skills/inventory-testing/SKILL.md) | 棚卸の受入条件に沿ってCSV、集計、競合、再送、障害復旧、売りex連携を検証する。 | 本プロジェクト作成。外部コード転用なし。実装に応じた実行環境を使用 |

全5件はプロジェクト独自の手順書で、外部skillの複製はない。リポジトリ全体のライセンスは未設定であり、第三者への再配布条件を別途定める。

`.agents/skills` の検出に対応したクライアントではリポジトリのskillを利用する。自動検出しないクライアントでも、AGENTS.mdとSKILL.mdを明示的に読むことで同じ手順を使える。全クライアントで自動有効化されることは保証しない。

## 外部skill

クラウド環境の初期セットアップには次のサービス提供skillを使用した。サービス側のツールを必要とするため、本体のコピーではなく参照情報を共有する。

- `cloud-environment-onboarding:setup`: クラウド環境の準備・検証・設定保存。提供元: Cloud Environment Onboarding。
- `cloud-environment:cloud-environment-runtime`: 接続・資格情報・ネットワークの確認。提供元: Cloud Environment。

別端末・別クライアントで必要な場合は、その環境で提供状況を確認する。提供されていないツールを利用可能として扱わない。資格情報やプラグインの有効化状態はリポジトリから移行されない。

今後外部skillを取り込むときは、配布元URL、版またはコミット、ライセンス、必要ツールを記録する。再配布条件を確認するまでは本体をコピーしない。
