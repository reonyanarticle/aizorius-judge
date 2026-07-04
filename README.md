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
| [docs/PLAN.md](docs/PLAN.md) | 開発フェーズ（eval-first）と環境前提 |
| [docs/EVALUATION.md](docs/EVALUATION.md) | 4層評価（検索/単体/統合/外部）・データセット仕様・合格基準 |

## ステータス
- ゴールデンデータセット（125問・人間承認済み）、コア検索エンジン（Hybrid＋rerank＋親グループ返却）、生成層評価（110問で合格率100%・LLM-judge較正済み）まで完了。次は MCP 層の実装。工程の正本は [docs/PLAN.md](docs/PLAN.md)。

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

## ライセンス
- 本リポジトリ（コード・ドキュメント・評価データセット）は **MIT License**（[LICENSE](LICENSE)）。
- 外部データの取り込みは **CC0 / CC BY（帰属のみ）を優先**する。継承（share-alike）系は本体に混ぜず別ファイル＋個別表記に隔離し、非商用限定（NC）は取り込まない。方針の正本は [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §5。
- **総合ルール（CR）本文・カードテキストはリポジトリに含めない**（ローカルで取得・生成する → [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §5）。

### Fan Content Policy
AIzorius Judge は、Wizards of the Coast のファンコンテンツ・ポリシーに認められた非公式のファンコンテンツです。Wizards of the Coast の承認・後援を受けたものではありません。使用している素材の一部は Wizards of the Coast LLC の財産です。©Wizards of the Coast LLC.

*AIzorius Judge is unofficial Fan Content permitted under the Fan Content Policy. Not approved/endorsed by Wizards. Portions of the materials used are property of Wizards of the Coast. ©Wizards of the Coast LLC.*
