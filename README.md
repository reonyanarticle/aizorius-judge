# AIzorius Judge

> **AI + Azorius = AIzorius** — ラヴィニカの法と秩序のギルド「Azorius」に由来。

Magic: The Gathering のルール裁定を支援する **MCPサーバー**。Claude Desktop / Claude Code と連携し、AIがジャッジの肩代わりをする。

## これは何か（1分）
- 入力：ルール質問（例「飛行持ちは到達持ちにブロックされる？」）や カード名。
- 処理：総合ルール（CR）の Hybrid Search（Vector＋BM25＋RRF＋rerank）と Scryfall API で、関連ルール・カード情報・公式裁定を返す。
- 裁定の**生成はクライアント側のLLM**（Claude Desktop / Claude Code）が行う。MCPサーバーは「情報検索の道具箱」に徹する。
- **すべてローカル・無料**：サーバー内でLLMを呼ばず、Embedding も Sentence Transformers でローカル実行（APIキー不要）。

## アーキテクチャ（要点）
```
Claude Desktop / Claude Code（推論・裁定生成・CR番号の実在性確認）
        │ MCP (stdio)
        ▼
AIzorius Judge MCPサーバー ※LLM呼び出しなし
  ├─ search_rules      … CR の Hybrid Search（Vector+BM25 → RRF → rerank）
  ├─ lookup_card       … Scryfall カード情報（日英 fuzzy）
  └─ get_card_rulings  … Scryfall 公式裁定
  └─ ChromaDB（永続化）← ローカルEmbedding（Sentence Transformers / MPS）
```
詳細は [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## ドキュメント
索引は [docs/README.md](docs/README.md)。主なもの：

| ファイル | 内容 |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 構成・実行フロー・ツール契約・検索/データパイプライン |
| [docs/PLAN.md](docs/PLAN.md) | 開発フェーズ（Phase 0〜4・eval-first）と環境前提 |
| [docs/EVALUATION.md](docs/EVALUATION.md) | 4層評価（検索/単体/統合/外部）・データセット仕様・合格基準 |

## ステータス
- フェーズ：設計完了、**Phase 0（データ基盤＋ゴールデンデータセット）着手前**。コードは未実装。開発は eval-first（dataset が先、MCP化は後）→ [docs/PLAN.md](docs/PLAN.md)。

## セットアップ
```bash
# Python 3.12 / uv
uv sync
cp .env.example .env   # 任意（デフォルトで動く。EMBEDDING_MODEL / EMBEDDING_DEVICE / DATA_DIR）
```
- APIキー不要（Scryfall は認証不要、Embedding はローカル）。外部評価を使う場合のみ `GPT4_API_KEY`。
- 開発機の想定：Apple Silicon Mac（MPS加速）。無い場合は CPU にフォールバック。

## 開発者向け
- 開発のルール・禁止事項・アーキ要点は **[CLAUDE.md](CLAUDE.md)**（詳細ルールは [.claude/rules/](.claude/rules/) に集約）。
- Python の細則（uv / Ruff / Black / basedpyright / 型ヒント）は [.claude/rules/python.md](.claude/rules/python.md)。
