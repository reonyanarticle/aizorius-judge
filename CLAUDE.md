# CLAUDE.md（AIzorius Judge 開発ガイド）

作業前に必読。docs索引は [docs/README.md](docs/README.md)。
詳細ルールは `.claude/rules/`（自動ロード）に集約する。本書は要約とポインタ。

## 禁止事項（必須・詳細は .claude/rules/）
- ❌ **MCPサーバー内でLLMを呼ばない**。`anthropic` / `openai` を通常依存に入れない（評価用 `openai` のみ `optional-dependencies` の `eval`）→ [.claude/rules/coding.md](.claude/rules/coding.md)。
- ❌ ツールを3つ（`search_rules` / `lookup_card` / `get_card_rulings`）以外に**安易に増やさない**。ツールは検索結果を返すだけで、要約・裁定生成をしない。
- ❌ Embedding に外部API（OpenAI等）を使わない。**Sentence Transformers でローカル実行**（mps / cpu フォールバック）。
- ❌ データ更新（差分検出・再インデックス）にLLMを使わない。文字列比較で行う。
- ❌ Scryfall へのリクエストで**レート制限を無視しない**（リクエスト間 50–100ms sleep、User-Agent 付与）。

## 開発ルール（詳細＝[.claude/rules/coding.md](.claude/rules/coding.md)）
- Python 3.12 / 依存は uv / lint=Ruff・整形=Black・型=basedpyright / pytest。細則＝[.claude/rules/python.md](.claude/rules/python.md)。
- I/O・設定は Pydantic で型定義。**型は `src/aizorius_judge/models.py`、設定は `src/aizorius_judge/settings.py`（pydantic-settings）に集約**。
- I/O（Scryfall呼び出し等）は `async`/`await`。CPUバウンド（Embedding計算等）は安易に `async` 化しない。
- 該当なしはエラーではなく分かりやすいメッセージを返す。

## ドキュメント作成ルール
- `docs/` 直下フラット・ファイル名は**全大文字**。**図は mermaid**（目的別に標準図種を使い分ける）。1テーマ1ファイル＝正本 → [.claude/rules/documentation.md](.claude/rules/documentation.md)。

## アーキテクチャ要点
- **MCPは「情報検索の道具箱」に徹し、考えるのはクライアント側のLLM**（Claude Desktop / Claude Code）。すべてローカル・無料で完結。
- FastMCP（stdio）＋ ChromaDB（永続化・cosine）＋ ローカルEmbedding（`paraphrase-multilingual-MiniLM-L12-v2`）。
- 検索は Hybrid：Vector＋BM25 → RRF融合 → Cross-Encoder rerank。
- カード情報・公式裁定は Scryfall API（認証不要・日英fuzzy対応）。
- 詳細：[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## テスト/検証
- **eval-first**：dataset が唯一の物差し。検索単体（recall@5・pytest）／ツール単体（pytest）／統合（Claude Code＋eval-runner）／外部（GPT-4o・任意）の4層 → [docs/EVALUATION.md](docs/EVALUATION.md)。
- 合格基準：recall@5≥0.8（検索）、スコア≥7/10・全体精度80%以上（統合）。Commander（統率者戦）関連を厚めに。

## サブエージェント / skill / hook
- サブエージェント：`dataset-curator`（opus・memory付き）＝golden datasetの作成・拡充と出典検証。`eval-runner`（sonnet・memory付き）＝統合評価の実行と回帰検知。`critical-reviewer`（opus）＝設計・計画・前提の批判的点検。コード差分の検証はユーザーレベルの `tech-lead-reviewer`。
- skill：`/qa`（Ruff→Black→basedpyright→pytest を通るまで）、`/mcp-smoke`（3ツールの実挙動をPASS/FAIL）、`/eval`（eval-runnerへ委譲）、`/commit`（混入チェック込みの日本語コミット）、`/docs-check`（docs規約リンター）。
- hook：`py-format.sh`（編集した`.py`をBlack+Ruff自動整形）／`stop-gate.sh`（未コミットの`.py`変更があるターン終了時に品質ゲートを回し、失敗ならblockして自己修正させる。2周目は素通し）。
- 実装の区切りでは `/qa` → `/mcp-smoke` →（検索に触れたら）`/eval` の順で自己検証してから完了報告する。

## 実装フェーズ（eval-first）
- Phase 0: データ基盤＋ゴールデンデータセット → Phase 1: コア検索エンジン（MCP非依存・recall測定しながら） → Phase 2: MCP層＋Scryfall → Phase 3: 統合評価＋拡充 → Phase 4: 自動更新。詳細：[docs/PLAN.md](docs/PLAN.md)。
