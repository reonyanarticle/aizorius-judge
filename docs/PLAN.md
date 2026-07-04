# Plan（開発フェーズと環境前提）

実装順の正本。**評価駆動（eval-first）**：ゴールデンデータセットと測定手段を先に作り、コア検索を測りながら作り込み、**回答（裁定）の品質を確立してから**MCPの皮を被せる。各フェーズの技術詳細は [ARCHITECTURE.md](ARCHITECTURE.md)、評価は [EVALUATION.md](EVALUATION.md)。
**フェーズ番号の記載は本ファイルのみ**（他の doc・rules・コード・レポートはフェーズ番号を書かず、本ファイルへのリンクで参照する → [.claude/rules/documentation.md](../.claude/rules/documentation.md)）。

## 開発フェーズ（実装順）

| Phase | 内容 | 完了条件 |
|---|---|---|
| **0. データ基盤＋ゴールデンデータセット** | CR原文の入手・**利用条件の一次確認**・版固定（発効日＋ハッシュ）、`parse_rules.py`（CR→JSON）、評価データセット110問（起案100＋公式リリースノートFAQ由来10）の作成・**出典検証・人間承認**、Embeddingモデルのスパイク検証（bake-off） | dataset 110問が出典検証済み＋人間承認済み／CR JSONが生成できる／Embedding方針が確定 |
| **1. コア検索エンジン（MCP非依存）** | `data_loader.py`（ChromaDB＋BM25）、`search.py`（Hybrid＋融合＋rerank）、`models.py`/`settings.py`。datasetを正解として**検索単体評価を測りながら**、融合方式・rerank・言語戦略をチューニング。あわせて**ライブラリ直呼びで数問 end-to-end 採点**し、検索指標と裁定品質の相関を確認 | **must_cite recall@5 ≥ 0.8**（[EVALUATION.md](EVALUATION.md) の基準）／代理指標の相関確認済み |
| **1.5. 生成層（裁定）の評価** | MCP化の前に**回答そのものの品質**を確立する。ライブラリ直呼びで全110問の裁定を生成し、`evaluation/test_runner.md` の手順で採点。**サマリ＋代表例のレポート**を `evaluation/reports/` に保存（人間が回答を確認できる形） | 各問スコア≥7/10・全体精度80%以上 → **達成（96.4%・平均9.30）**。LLM-judge較正（16問の人間採点）は **実施済**（2026-07-04：合否一致 87.5%・±1点一致 56.3%。分析は `evaluation/reports/generation-eval.md`。ルーブリック調整の要否はユーザー判断待ち） |
| **1.6. 評価フィードバックの反映（検索改善・バグ修正・dataset拡充）** | 生成層評価・LLM-judge較正・コード/設計レビュー（2026-07-04）で見つかった課題の解消。**課題の全件リストは下記「評価フィードバック反映の課題一覧」**。①**重大バグ2件の修正＋単体テスト補強** ②**検索改善**（優先順）：セクション内 timing/定義ルール（704.3/903.3等）の決定論的同伴 → 用語集明示ヒットの最終グループ枠保証。各施策は recall/MRR の劣化を同時計測して採否 ③**評価プロトコル改善**：言い換え反復は実LLMに元質問だけ渡して生成させる（手書き固定クエリは評価汚染のため不可） ④中・軽微の指摘とテストの穴の解消（下記一覧） ⑤~~card_interactions の人間承認と統合~~ **済**（2026-07-04 承認・125問統合・検索単体評価から除外） ⑥~~LLM-judgeルーブリックの調整判断~~ **済**（2026-07-04 ユーザー決定：引用重視を維持） | 重大バグ2件が修正されテストで再発防止／検索改善後の must_cite recall@5 が 0.850 から劣化せず、検索起因の不合格4問のうち2問以上を回収／下記一覧の中・軽微が対応済みまたは明示的に見送り判断済み |
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

## 評価フィードバック反映の課題一覧（2026-07-04 レビュー3本の全指摘）

コード全体レビュー（tech-lead）・設計反証レビュー（critical-reviewer）・規約準拠レビュー（rules-reviewer）の指摘を漏れなく列挙する。対応順の方針は上表の①〜④。見送る場合も理由を記録してからクローズする。

### 重大（必修・実データで再現確認済み）
1. **ルール番号直接引きの前方一致境界バグ**（`search.py` `_direct_number_lookup` の `startswith`）：`"702.9"` の直接引きに無関係な 702.90〜702.99 系が35件混入。「番号ズバリ引きは正確」という契約が2桁サブ番号を持つ全セクションで破れる。修正は「完全一致 or 直後が英字1文字」の境界明示＋専用テスト。
2. **用語集のルール参照抽出が複数形・範囲表記を取りこぼす**（`rules_parser.py` `_RULE_REF_RE`）：`"See rules 509.1b–c"` / `"rules 613.2, 707.2, and 707.3"` を抽出できず、実データで Evasion Ability から 509.1c が欠落（同型定義は16用語）。日本語訳の偶然の救済に依存しており、**日英版ズレ時は新規用語の参照が丸ごと空になる**。`_SECTION_REF_RE` にも同じ制約。修正は plural・enダッシュ範囲・列挙対応＋3パターンの専用テスト。

### 中
3. `scryfall.py` `_to_card`：両面カード（Transform/MDFC）の power/toughness/loyalty が `card_faces` にフォールバックせず常に None（oracle_text/mana_cost はフォールバック済み）。実戦頻出カード種でP/T欠落。
4. `data_loader.py` `build_or_load_index`：約75行に責務集中（fingerprint比較・コレクション再作成・バッチ投入・Reranker/BM25構築・用語集ロード）＋ `get_collection` の `except Exception` が広すぎ、DB破損等も黙って再構築に化ける。分割と例外の絞り込み。
5. **MCP層実装時の地雷（設計メモ）**：`HybridSearcher.search()` は同期のCPU/GPUバウンド（BM25・Embedding・rerank）。ツール層から直接 `await` せず `asyncio.to_thread` 等でイベントループ外へ（→ [.claude/rules/python.md](../.claude/rules/python.md) §5/§7）。
6. `settings.py` `data_dir=Path("data")` が相対パス既定：stdio起動（Claude Desktop等・CWD不定）で `data/` を見失うリスク。lifespan実装時に絶対化 or `.env` 明示を要検討。
7. `scripts/eval_retrieval.py` が `searcher._index`（private属性）へ直接アクセス：`HybridSearcher` に読み取り用アクセサを公開してカプセル化を回復。
8. `scryfall.py`：rulings取得（2段目）の404が `CardNotFoundError`（「カードが見つからない」）に化ける／`response.json()` のデコード失敗が `ScryfallError` に包まれず素の例外で漏れる。

### 軽微
9. `search.py` 直接引きのソートが文字列比較（`"702.10"` が `"702.2"` より前）。修正時に数値キー化（重大1と同根箇所）。
10. `max_groups`（実装）と `max_results`（ARCHITECTURE.md §3 のツール契約）の命名不一致。MCP層実装時に統一。
11. 全角/半角の正規化（NFKC等）が `tokenize` / `_glossary_ranking` に無く、日本語の罠（全角半角・表記ゆれ）の専用テストも未整備（[.claude/rules/coding.md](../.claude/rules/coding.md) の要求）。
12. 日本語CRのHTML抽出（`rules_parser.py`）が `div`/`br` をブロック境界として扱わない＋`parse_rules.py` にパース後の自己検証（総ルール数・英日カバレッジ差のアサーション）が無い。サイト構造変更時に静かに壊れる。
13. `models.py` `CorpusEntry.embedding_text()`：型定義モジュールに整形ロジックが同居（許容範囲だが境界の明確化を検討）。
14. `search.py` `group_by_parent`：親がコーパスに無いグループが `max_groups` の枠を消費してから捨てられる経路への防御（現行データでは未到達）。
15. `scripts/prepare_generation_contexts.py` の `sys.path` 裸import（scripts間依存。共通ロジックはパッケージ側へ）／`render_group`・`report_generation_eval.py` の docstring 欠落／`.gitignore` の冗長行（`gen-eval/contexts.jsonl` は `gen-eval/` と重複）。

### テストの穴（重大1・2を見逃した直接原因。重大の修正とセットで補強）
- `search.py`：`group_by_parent` / `parent_of` / `_direct_number_lookup` / `_glossary_ranking` のテストが0件。
- `rules_parser.py`：`parse_glossary_en` / `parse_glossary_ja` / `merge_glossaries` / `_referenced_rules` のテストが0件。
- `data_loader.py`：`load_glossary_terms`（セクション上限分岐）・`_source_fingerprint`・再構築判定が未テスト。
- `scryfall.py`：`_to_card` の `card_faces` フォールバック分岐が未テスト。
- `scripts/validate_dataset.py`：subset検査（cited⊆relevant 等）ロジック自体のテストが無い（データセット品質ゲートの自己検証）。

### 検索改善の設計方針（反証レビューで確定した優先順位）
- 「実運用の反復検索で救われる」に依存しない：生成層評価は決定論的2クエリ通過後の失敗であり、救済言い換えにはクライアント側のMTG知識が要る（未測定）。
- 最優先はグループ化粒度の構造穴（同一セクション内の別親、例 704.5f と 704.3 が非同伴）への対処。rerank pool への兄弟投入は distractor 増で棄却済みだが、**rerank後の勝ちグループへの同伴は未検証**。
- 口語同義語の用語集追加は**過学習リスクで降格**：足す場合は hold-out の口語クエリで汎化確認を条件とする。
- 詳細な経緯・実測値は `evaluation/reports/generation-eval.md` の「検索起因4問の原因分析」。

## Phase 2 の補足
- `.mcp.json` の dev サーバー登録（`{"command": "uv", "args": ["run", "aizorius-judge"]}`）は**サーバーが起動可能になってから**追加する（それ以前に置くとセッション開始のたびに接続エラーになる）。
- 接続後は `/mcp-smoke` → Claude Desktop（stdio）の順で確認。

## 環境・前提
- **開発機**：MacBook Pro M4 / 32GB / macOS 15.x（MPS加速が使える）
- **Python**：3.12（uv 管理 → [.claude/rules/python.md](../.claude/rules/python.md)）
- **APIキー**：不要（Scryfall は認証不要、Embedding はローカル）。外部評価を使う場合のみ `GPT4_API_KEY`
- **環境変数**（すべて任意、デフォルトで動く）：`EMBEDDING_MODEL` / `EMBEDDING_DEVICE`（mps|cpu）/ `DATA_DIR`
