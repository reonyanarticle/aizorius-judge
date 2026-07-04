# Evaluation（評価アーキテクチャ）

評価設計の正本。**dataset を唯一の物差し**として、検索単体（retrieval）→ ツール単体 → 統合（裁定品質）→ 外部の4層で測る。dataset は実装より先に作る（eval-first → [PLAN.md](PLAN.md)）。

## 1. 4層構成

| 層 | 対象 | 手段 | 頻度 / コスト |
|----|------|------|--------------|
| 1. 検索単体評価 | Hybrid Search の検索品質（MCP非依存） | dataset の `retrieval_relevant_rules` を正解として **recall@5 / MRR** を pytest で測定（`tests/test_search.py`） | 毎コミット / $0 |
| 2. ツール単体テスト | MCPツールのI/O・整形・エラー処理 | pytest（`tests/test_mcp_tools.py`、Scryfallはモック） | 毎コミット / $0 |
| 3. 統合評価 | クライアントの推論・裁定品質 | Claude Code＋eval-runner サブエージェントで `evaluation/dataset.jsonl` を実行（`evaluation/test_runner.md` の手順） | 開発時・週次 / $0 |
| 4. 外部評価 | 総合精度のダブルチェック | GPT-4o LLM-as-a-Judge（`scripts/run_external_eval.py`） | リリース前・任意 / ~$5 |

- 評価の中心は **Claude Code**（開発環境に統合、追加コストなし）。外部LLM評価はオプション。
- 第1層が**コア検索チューニングの物差し**（RRF α・rerank有無・チャンク粒度をこれで決める）。第3層は MCP と推論を含めた最終品質。

## 2. 合格基準

| 層 | 基準 |
|---|---|
| 検索単体（主指標） | **must_cite recall@5 ≥ 0.8**（裁定の核となるルールが top5 グループに入る割合。実測 0.850 単一クエリ / 0.914 反復検索2クエリ模擬） |
| 検索単体（追跡指標） | recall@5（完全集合ベース・実測 0.681、目標 0.6 達成）と MRR（実測 0.783）を継続計測 |
| 統合評価 | 各問スコア ≥7/10 で合格、全体精度 80% 以上を目標（生成層評価＝ライブラリ直呼びの実測 **96.4%**・平均9.30。検索改善＋7グループ返却での再評価後。サマリは `evaluation/reports/generation-eval.md`） |

- 検索単体の測定は**単一クエリ（下限）と反復検索模擬（実運用相当）の両方**で行う（`scripts/eval_retrieval.py --multi`）。実運用ではクライアントLLMが角度を変えたクエリを反復発行するため、単一クエリの数値は保守的な下限になる。

- **層間ゲート**：検索単体（第1層）が基準未達のうちは、統合評価（第3層）のスコア改善に投資しない（検索が正解を返せない状態で推論側を調整しても徒労になる）。
- **LLM-judge の較正**：統合評価（第3層）の初回実行時に15〜20問を人間も採点し、eval-runner の採点との一致率（±1点以内の割合）を確認して採点プロンプトを較正する。LLM採点を人間採点で統計的に裏付ける構成は RAG 評価の先行研究（ARES の PPI 等）に倣う。生成層評価での実測（16問・2026-07-04）：**合否一致 87.5%・±1点一致 56.3%、LLM採点は人間より系統的に辛い**（must_cite 欠落の減点が人間評価より重い）。分析は `evaluation/reports/generation-eval.md`。
- **代理指標の相関確認**：recall@5 を上げても裁定品質（7/10）が動かない事態を早期に検知するため、コア検索の段階で MCP を介さずライブラリ直呼びで数問だけ end-to-end 採点し、両指標の相関を確認する（→ [PLAN.md](PLAN.md)）。
- 回帰：前回レポートより下がった問題は最優先で報告・対処する（eval-runner が検知）。

## 3. 評価データセット（`evaluation/dataset.jsonl`）
110問（起案100＋公式リリースノートFAQ由来10）を実装より先に作成し、必要に応じて拡充する（時期は [PLAN.md](PLAN.md)）。
**形式は JSONL（1問=1行）の単一ファイル**。評価データセットの事実上の標準（OpenAI evals / Hugging Face datasets）に合わせる。1行=1問なので git diff が問単位になり、追記・行単位ツール（jq等）とも相性がよい。カテゴリはファイル分割でなく各問の `category` フィールドで表す。各問のスキーマ：

| フィールド | 内容 |
|---|---|
| `question` | ルール質問（日本語） |
| `expected_tools` | 期待されるツール呼び出し（例 `["search_rules", "lookup_card"]`） |
| `expected_answer.conclusion` | 期待される結論 |
| `expected_answer.rules_cited` | 回答で**引用すべき**CR番号 |
| `expected_answer.key_facts` | 回答に含むべき重要事実 |
| `retrieval_relevant_rules` | 検索が返すべきルール番号の**完全集合**（`rules_cited`＋裁定を支える周辺ルール）。**検索単体評価（recall@k）の正解はこちら**。引用用と検索用を分けるのは、引用番号だけで recall を測ると過小評価になり融合・rerank を誤調整するため |
| `source` | 出典（照合したCRの発効日版）。全問必須 |
| `notes` | 網羅性への注記・保留事項（任意） |
| `evaluation_criteria.must_cite_rules` | 必ず引用すべきルール |
| `evaluation_criteria.forbidden_mistakes` | してはいけない誤り |

### 品質要件（datasetの信頼性がすべての層の上限になる）
- **出典検証必須**：`rules_cited` / `retrieval_relevant_rules` はCR原文と照合し、実在・引用妥当性・版（発効日）を確認してから確定する（dataset-curator サブエージェントの仕事）。
- **ルール正誤の最終署名は人間**：LLM（dataset-curator 含む）は出典照合・実在チェック・差分提示までを担い、正解データとして確定する承認は人間が行う。本プロジェクトはハルシネーション対策を売りにするため、**LLM生成の「正解」をLLMで採点する自己参照**を評価基盤に持ち込まない。
- **正解データの作り方が評価を汚染しないよう注意**：`retrieval_relevant_rules` を特定の検索手段（キーワードgrepだけ等）で集めると、その方式に有利な正解になる。CRの目次・関連ルール参照（"See rule …"）もたどって網羅する。網羅に自信がない問は `notes` に残す。
- 期待値の誤りを見つけたら、採点側で辻褄を合わせず dataset を修正する（修正は出典つきで・人間承認を経る）。

### カテゴリ（110問の配分）
| カテゴリ | 問数 | 範囲の目安 |
|---|---|---|
| `basic_rules` | 22 | ターン構造・唱える手順・対象・状況起因処理の基本 |
| `stack_priority` | 19 | スタック・優先権・解決順・呪文/能力への対応 |
| `combat` | 17 | 攻撃/ブロック指定・戦闘ダメージ・飛行/到達等の回避能力 |
| `keywords` | 16 | キーワード能力（702）・キーワード処理 |
| `commander` | 25 | **厚めに**：統率者税・統率者ダメージ・色アイデンティティ・統率領域（→ [ARCHITECTURE.md](ARCHITECTURE.md) §6） |
| `layers` | 6 | 種類別（613）・タイムスタンプ・依存 |
| `replacement_effects` | 5 | 置換・軽減効果（614/615）・適用順 |

## 4. 実行手順
- 検索単体：`uv run pytest tests/test_search.py`（recall@5 / MRR を assert）。
- 統合評価：`/eval`（eval-runner に委譲）。手順の正本は `evaluation/test_runner.md`、レポートは `evaluation/reports/`。
- 外部評価：`uv run scripts/run_external_eval.py`（要 `GPT4_API_KEY`。openai は `eval` optional-dependencies）。
