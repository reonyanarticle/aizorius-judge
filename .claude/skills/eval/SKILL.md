---
name: eval
description: 評価データセット(evaluation/dataset.json)による統合評価を実行する。「評価して」「evalして」「精度を測って」「回帰チェック」で起動、または検索ロジック・インデックス・Embeddingモデルを変更したあとに積極的に使う。実行はeval-runnerサブエージェントに委譲し、スコアと前回比を報告する。
model: inherit
allowed-tools: Agent, Read, Grep, Glob
---

# /eval — 統合評価の実行（eval-runner へ委譲）

[docs/EVALUATION.md](../../../docs/EVALUATION.md) の第2層（統合テスト）を回す。MCPツールの単体テスト
（pytest）とは**別物**で、クライアント推論込みの裁定品質を測る。

## 手順
1. `evaluation/dataset.json` の存在を確認する。無ければ「Phase 4 未着手のため実行不可」と報告して終了。
2. **eval-runner サブエージェント**を起動し、評価の実行・採点・レポート作成を委譲する
   （手順の正本は `evaluation/test_runner.md` と eval-runner の定義）。
3. 完了後、次を要約して報告する：
   - 全体スコア（合格=各問≥7/10、目標=精度80%以上）
   - カテゴリ別（basic_rules / stack_priority / commander …）の内訳
   - **前回レポートとの差分**（劣化した問題があれば最優先で列挙＝回帰検知）
   - レポートの保存先（`evaluation/reports/`）

## 注意
- 評価中の裁定生成で引用したCR番号は `search_rules` で実在確認する（Hallucination対策の運用そのもの）。
- スコアが目標未達でも自動で「合格」と言い換えない。未達は未達として報告し、劣化原因の当たりを添える。
