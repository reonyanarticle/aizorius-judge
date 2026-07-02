# コーディング規約（AIzorius Judge 固有）

AIzorius Judge の実装に従うルール。コードは未着手だが、Phase 1 着手時からこれを守る。言語・ツールの細則は [[python]]。

## 言語・ツール
- **Python 3.12**。依存管理は **uv**。**lint＝Ruff／整形＝Black／型＝basedpyright**。詳細は [[python]]。
- ツールI/O・設定は **Pydantic** で型定義する。ツール契約の正本は [ARCHITECTURE.md](../../docs/ARCHITECTURE.md) §3。
- **型は `src/aizorius_judge/models.py`、設定は `src/aizorius_judge/settings.py`（pydantic-settings）に集約**（→ [[python]] §0）。

## LLM・コスト（最重要）
- **MCPサーバー内でLLMを呼ばない**。推論・裁定生成はクライアント（Claude Desktop / Claude Code）の責務。
- 依存に **anthropic / openai を入れない**。評価用 openai は `[project.optional-dependencies]` の `eval` のみ。
- **Embedding はローカル実行**（Sentence Transformers）。外部Embedding API（OpenAI等）を使わない。デバイスは `mps`、フォールバック `cpu`（`settings.py` の `EMBEDDING_DEVICE`）。
- **データ更新（差分検出・再インデックス）にもLLMを使わない**。文字列比較・ハッシュ比較で行う。

## ツール設計
- ツールは **3つに限定**：`search_rules` / `lookup_card` / `get_card_rulings`。安易に増やさない（増やすなら設計判断として docs に記録）。
- すべて**検索結果を返すだけ**。要約・裁定生成・意見の付与をしない。
- **該当なしはエラーではなく分かりやすいメッセージ**を返す（クライアントLLMが次の行動を判断できる文面に）。

## 外部API（Scryfall）
- 呼び出しは **httpx で `async`**。リクエスト間に **50–100ms sleep**、**User-Agent を付与**（レート制限遵守）。
- クライアントは lifespan で生成し**注入**する（テストでモック差し替え可能に）。テストで実APIを叩かない。

## ログ・stdio
- 標準 `logging`（`logger = logging.getLogger(__name__)`）。**stdout に print しない**（stdio transport が壊れる）。ログは stderr へ。
- 検索ログ（クエリ・件数・所要時間）を最初から入れる。

## テスト・評価
- 検索品質の単体テスト（pytest）と、クライアント裁定品質の評価（`evaluation/`）は**別物**として扱う → [EVALUATION.md](../../docs/EVALUATION.md)。
- 日本語特有の罠（全角半角・カード名表記ゆれ・日英カード名・PDF抽出ゴミ）は専用テストを最初から置く。
