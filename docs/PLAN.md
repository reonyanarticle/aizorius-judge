# Plan（開発フェーズと環境前提）

実装順の正本。**評価駆動（eval-first）**：ゴールデンデータセットと測定手段を先に作り、コア検索を測りながら作り込み、**回答（裁定）の品質を確立してから**MCPの皮を被せる。各フェーズの技術詳細は [ARCHITECTURE.md](ARCHITECTURE.md)、評価は [EVALUATION.md](EVALUATION.md)。
**フェーズ番号の記載は本ファイルのみ**（他の doc・rules・コード・レポートはフェーズ番号を書かず、本ファイルへのリンクで参照する → [.claude/rules/documentation.md](../.claude/rules/documentation.md)）。

## 開発フェーズ（実装順）

| Phase | 内容 | 完了条件 |
|---|---|---|
| **0. データ基盤＋ゴールデンデータセット** | CR原文の入手・**利用条件の一次確認**・版固定（発効日＋ハッシュ）、`parse_rules.py`（CR→JSON）、評価データセット110問（起案100＋公式リリースノートFAQ由来10）の作成・**出典検証・人間承認**、Embeddingモデルのスパイク検証（bake-off） | dataset 110問が出典検証済み＋人間承認済み／CR JSONが生成できる／Embedding方針が確定 |
| **1. コア検索エンジン（MCP非依存）** | `data_loader.py`（ChromaDB＋BM25）、`search.py`（Hybrid＋融合＋rerank）、`models.py`/`settings.py`。datasetを正解として**検索単体評価を測りながら**、融合方式・rerank・言語戦略をチューニング。あわせて**ライブラリ直呼びで数問 end-to-end 採点**し、検索指標と裁定品質の相関を確認 | **must_cite recall@5 ≥ 0.8**（[EVALUATION.md](EVALUATION.md) の基準）／代理指標の相関確認済み |
| **1.5. 生成層（裁定）の評価** | MCP化の前に**回答そのものの品質**を確立する。ライブラリ直呼びで全110問の裁定を生成し、`evaluation/test_runner.md` の手順で採点。**サマリ＋代表例のレポート**を `evaluation/reports/` に保存（人間が回答を確認できる形） | 各問スコア≥7/10・全体精度80%以上 → **達成（96.4%・平均9.30）**。LLM-judge較正（16問の人間採点）は **実施済**（2026-07-04：合否一致 87.5%・±1点一致 56.3%。分析は `evaluation/reports/generation-eval.md`。ルーブリック調整の要否はユーザー判断待ち） |
| **2. MCP層＋Scryfall** | FastMCPサーバー＋3ツール＋lifespan、Scryfall asyncクライアント（レート制限・**利用規約の一次確認**）、Scryfall の**contract test**（記録済みfixture＋任意のlive実行マーク）、`.mcp.json` 登録、Claude Desktop接続 | `/mcp-smoke` 全PASS |
| **3. 統合評価＋拡充** | MCP経由での統合評価（1.5 のライブラリ直呼び結果と比較し、MCP層で品質が落ちていないことを確認）、回帰検知の運用開始、datasetの拡充（必要に応じて。手薄なカテゴリの追補）、外部評価（任意） | 各問スコア≥7/10・全体精度80%以上（MCP経由） |
| **4. 自動更新** | `rules_updater.py`（差分検出・段階更新、LLM不使用）、`check_updates.sh`（cron） | CR更新時に変更分のみ再インデックスされ、検索評価が劣化しない |

- 自動更新を最後に置く理由：CRの改訂はセット発売ごと（数か月周期）で、後回しの実害が小さい。逆に dataset を先頭に置く理由：検索・裁定の**品質はすべて dataset を物差しに測る**ため、物差しが無いままの実装・チューニングは手戻りになる。

## Phase 0 の着手内容（最初にやること）
1. **CR原文の入手と利用条件の一次確認**：英語CR（Wizards公式のTXT）と日本語CR（mtg-jp.com）をダウンロードし、フォーマットを確認する。**パース済みJSONのリポジトリ保存・配布の可否は Wizards Fan Content Policy／CR配布ページの利用条件・mtg-jp.com の再利用条件を一次情報で確認**する（推測で進めない）。**入手できない/パースできない/保存できない場合はここで方式を再検討**（以降の全フェーズが依存するため最初に潰す）。
2. **版固定**：CRの発効日とファイルハッシュを記録し、**日英CRの版ズレ**（日本語CRは英語版に遅れうる）を検知できるようにする。評価と索引が別版のCRを見る不整合を防ぐ。
3. **`scripts/parse_rules.py`**：CR TXT → JSON（`{number, text, section, category}`）。日本語CRも同スキーマで。ルール番号の対応（英日で同一番号）を確認。
4. **ゴールデンデータセット110問（起案100＋公式リリースノートFAQ由来10）**（`evaluation/dataset.jsonl`）：スキーマは [EVALUATION.md](EVALUATION.md) §3。dataset-curator サブエージェントが**CR原文と照合して出典検証**し、**正解としての最終承認は人間**が行う（LLM生成の正解をLLMで採点する自己参照を避ける）。カテゴリは basic_rules / stack_priority / commander から開始。
5. **Embeddingスパイク（bake-off）**：候補モデル複数でCRをインデックスし、dataset の日本語クエリで recall@5 を比較して**モデルとインデックスの言語戦略（日英併記/別建て）を決定**する（コア実装に入る前に方式リスクを潰す）。結果と決定は [ARCHITECTURE.md](ARCHITECTURE.md) §4 と `evaluation/reports/spike-embedding.md`。
- `pyproject.toml`（uv / Ruff / Black / basedpyright / pytest 設定）、`src/aizorius_judge/` の骨格、CI（GitHub Actions：lint・型・テストの必須化 → [.claude/rules/python.md](../.claude/rules/python.md) §8）もこのフェーズで用意する。

## Phase 2 の補足
- `.mcp.json` の dev サーバー登録（`{"command": "uv", "args": ["run", "aizorius-judge"]}`）は**サーバーが起動可能になってから**追加する（それ以前に置くとセッション開始のたびに接続エラーになる）。
- 接続後は `/mcp-smoke` → Claude Desktop（stdio）の順で確認。

## 環境・前提
- **開発機**：MacBook Pro M4 / 32GB / macOS 15.x（MPS加速が使える）
- **Python**：3.12（uv 管理 → [.claude/rules/python.md](../.claude/rules/python.md)）
- **APIキー**：不要（Scryfall は認証不要、Embedding はローカル）。外部評価を使う場合のみ `GPT4_API_KEY`
- **環境変数**（すべて任意、デフォルトで動く）：`EMBEDDING_MODEL` / `EMBEDDING_DEVICE`（mps|cpu）/ `DATA_DIR`
