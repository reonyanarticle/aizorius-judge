# docs 索引

迷ったらここ。1テーマを1ファイルにし、それを正本にする（重複させない）。命名、図、書き方の規約は [.claude/rules/documentation.md](../.claude/rules/documentation.md)。

## 設計
- [ARCHITECTURE.md](ARCHITECTURE.md) … 確定した設計判断・構成（コンテナ図）・実行フロー（シーケンス図）・MCPツール契約・検索/データパイプライン・品質/安全設計・ディレクトリ構造

## 計画
- [PLAN.md](PLAN.md) … 開発フェーズ（Phase 0〜4・eval-first）・Phase 0 着手内容・環境前提

## 評価
- [EVALUATION.md](EVALUATION.md) … 4層評価（検索単体/ツール単体/統合/外部）・層間ゲート・データセット仕様・合格基準

## 開発の進め方
- 禁止事項・コーディング/ドキュメントのルールは [../CLAUDE.md](../CLAUDE.md) と [../.claude/rules/](../.claude/rules/)
- Python 細則（uv / Ruff / Black / basedpyright）は [../.claude/rules/python.md](../.claude/rules/python.md)

## 読む順の目安
1. ARCHITECTURE（設計判断と構成）
2. PLAN（進め方）
3. EVALUATION（品質の測り方）
4. CLAUDE.md と .claude/rules/（実装に入るとき）
