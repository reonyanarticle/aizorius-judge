# test_runner — 生成層（裁定）評価の実行手順（正本）

`evaluation/dataset.jsonl` の全問に対して裁定を生成し、golden 基準で採点する手順。
実行の主体は Claude Code（eval-runner サブエージェント）。時期の位置づけは [../docs/PLAN.md](../docs/PLAN.md)。

## 原則
- **生成と採点を分離する**：裁定を書いたエージェントは自分の裁定を採点しない（自己満点バイアス防止）。
- **生成は検索結果のみを根拠にする**：モデルの記憶にあるルール知識で補完しない。検索結果に根拠が無い場合は
  「根拠不足」と明記した裁定を書く（それが検索の弱点の検出になる）。
- **採点は golden が正**：`expected_answer` / `evaluation_criteria` に照らして採点し、golden の誤りを疑う場合も
  採点は golden 基準で行い「dataset要修正候補」として別枠報告する。

## 手順
1. **検索コンテキストの事前計算**：`uv run python scripts/prepare_generation_contexts.py`
   → `evaluation/reports/gen-eval/contexts.jsonl`（品質構成＋反復検索2クエリ、上位グループの本文。
   CR本文を含むため**コミットしない**）。
2. **裁定生成**（生成エージェント・カテゴリ別バッチ）：各問について contexts の検索結果**だけ**を根拠に、
   日本語で裁定を書く。出力（1問=1行のJSONL・`gen-eval/answers-<batch>.jsonl`）：
   `{"id", "answer": {"conclusion": "...", "rules_cited": [...], "explanation": "..."}}`
   - conclusion: 結論（1〜3文）。explanation: 根拠の説明（引用ルール番号つき）。
   - 検索結果に根拠が無ければ conclusion に「検索結果からは確定できない」と書く（捏造しない）。
3. **採点**（判定エージェント・生成とは別インスタンス）：各問の生成裁定を golden と照合し10点満点で採点。
   出力（`gen-eval/scores-<batch>.jsonl`）：`{"id", "score": 0-10, "rationale": "...", "dataset_issue": null|"..."}`
   - 採点基準：結論の正誤（〜5点）／must_cite_rules の引用（〜3点）／key_facts の網羅（〜2点）。
     forbidden_mistakes に抵触したら結論点を0にする。
4. **集計とレポート**：`uv run python scripts/report_generation_eval.py`
   → コミットする `evaluation/reports/generation-eval.md` は**定量サマリ＋不合格詳細＋カテゴリ代表例**まで
   （[.claude/rules/documentation.md](../.claude/rules/documentation.md) の評価成果物のコミット方針）。
   **全問の裁定文**はローカルの `gen-eval/generation-eval-full.md`（gitignore済・再現は本手順1〜4）。
   人間が回答を確認する場所はこの2ファイル。
5. **LLM-judge較正**：スコア分布から15〜20問を抽出し、裁定文と golden を並べた較正シート
   （`gen-eval/calibration.md`）を作る。**人間が同じ基準で採点**し、LLM採点との一致率（±1点以内の割合）を
   確認する。大きくズレる場合は採点基準を修正して再採点する（→ [../docs/EVALUATION.md](../docs/EVALUATION.md) §2）。

## 合格基準
- 各問スコア ≥7/10 で合格、全体精度（合格率）80%以上（[../docs/EVALUATION.md](../docs/EVALUATION.md)）。
- 不合格問は「検索起因（根拠が取れていない）／生成起因（根拠はあるのに結論を誤った）／dataset起因」に
  分類してレポートに記録する（次の改善の入力にする）。
