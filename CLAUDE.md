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
- FastMCP（stdio）＋ ChromaDB（永続化・cosine）＋ ローカルEmbedding（`intfloat/multilingual-e5-base`・日英併記コーパス）。
- 検索は Hybrid：Vector（言語別）＋BM25＋用語集照合 → RRF融合 → 多言語rerank → **親ルール単位のグループで返却**。
- カード情報・公式裁定は Scryfall API（認証不要・日英fuzzy対応）。
- 詳細：[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## テスト/検証
- **eval-first**：dataset が唯一の物差し。検索単体（recall@5・pytest）／ツール単体（pytest）／統合（Claude Code＋eval-runner）／外部（GPT-4o・任意）の4層 → [docs/EVALUATION.md](docs/EVALUATION.md)。
- 合格基準：recall@5≥0.8（検索）、スコア≥7/10・全体精度80%以上（統合）。Commander（統率者戦）関連を厚めに。

## 進め方（対話ルール）
- **設計・計画・ドキュメントだけを頼まれたら、承認前に実装コードを書かない・足場を作らない**（スコープ確認が先）。深掘りは `design-planner` サブエージェントに委ねる。
- **共有・永続の設定**（`.claude/settings.json`・モデルピン等）は勝手に変更せず、**提案→承認**を経る。個人事情は local/user スコープへ。
- **成果物は検証してから完了報告**：ファイルが開ける・仕様に合う・テストが通ることを確認する（「たぶん動く」で渡さない）。

## サブエージェント / skill / hook（モデルは作業の重さで使い分ける）
- サブエージェント：`design-planner`（opus・コード禁止）＝設計・計画の立案。`dataset-curator`（opus・memory付き）＝golden datasetの作成・拡充と出典検証。`eval-runner`（sonnet・memory付き）＝統合評価の実行と回帰検知。`critical-reviewer`（opus）＝設計・計画・前提の批判的点検。`rules-reviewer`（sonnet）＝コード差分の CLAUDE.md／`.claude/rules/` 準拠チェック（修正せず報告のみ）。
- skill：`/test`（**haiku**・テスト実行と報告のみ）、`/qa`（**sonnet**・失敗を修正して通るまで）、`/commit`（**sonnet**・混入チェック込みの日本語コミット）、`/docs-check`（**sonnet**・docs規約リンター）、`/mcp-smoke`（sonnet・3ツールの実挙動をPASS/FAIL）、`/eval`（eval-runnerへ委譲）。
- hook：`py-format.sh`（編集した`.py`をBlack+Ruff自動整形）／`stop-gate.sh`（未コミットの`.py`変更があるターン終了時に品質ゲートを回し、失敗ならblockして自己修正させる。2周目は素通し）。
- 実装の区切りでは `/qa` → `/mcp-smoke` →（検索に触れたら）`/eval` →（docs/rulesに触れたら）`/docs-check` の順で自己検証してから完了報告する。

## 実装フェーズ（eval-first）
- データ基盤＋dataset → コア検索エンジン → **生成層（裁定）の評価** → MCP層＋Scryfall → 統合評価＋拡充 → 自動更新、の順。**フェーズ番号と正本は [docs/PLAN.md](docs/PLAN.md) のみ**（他所にフェーズ番号を書かない → [.claude/rules/documentation.md](.claude/rules/documentation.md)）。
