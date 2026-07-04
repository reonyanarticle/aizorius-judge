"""生成層評価の集計：answers/scores を dataset と突き合わせ、裁定文込みレポートを作る。

入力: evaluation/reports/gen-eval/answers-*.jsonl / scores-*.jsonl（test_runner.md の手順で生成）
出力: evaluation/reports/generation-eval.md（全問の裁定文・スコア・カテゴリ別集計・不合格一覧）

実行: uv run python scripts/report_generation_eval.py
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GEN_DIR = REPO_ROOT / "evaluation" / "reports" / "gen-eval"
PASS_SCORE = 7


def load_jsonl_glob(pattern: str) -> dict[str, dict[str, object]]:
    records: dict[str, dict[str, object]] = {}
    for path in sorted(GEN_DIR.glob(pattern)):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                records[str(record["id"])] = record
    return records


def main() -> int:
    questions = {
        str(q["id"]): q
        for q in map(
            json.loads,
            (REPO_ROOT / "evaluation" / "dataset.jsonl")
            .read_text(encoding="utf-8")
            .splitlines(),
        )
    }
    answers = load_jsonl_glob("answers-*.jsonl")
    scores = load_jsonl_glob("scores-*.jsonl")

    missing = [qid for qid in questions if qid not in answers or qid not in scores]
    if missing:
        print(f"未完了 {len(missing)}問: {missing[:10]}", file=sys.stderr)
        return 1

    all_scores = [int(scores[qid]["score"]) for qid in questions]  # type: ignore[arg-type]
    passed = sum(1 for s in all_scores if s >= PASS_SCORE)
    by_category: dict[str, list[int]] = defaultdict(list)
    for qid, question in questions.items():
        by_category[str(question["category"])].append(int(scores[qid]["score"]))  # type: ignore[arg-type]

    lines: list[str] = [
        "# 生成層（裁定）評価レポート",
        "",
        "全110問の裁定を検索結果のみを根拠に生成し、golden 基準で採点した結果（手順: evaluation/test_runner.md）。",
        "**このファイルが「回答（裁定文）を確認する場所」**。",
        "",
        f"- 合格（≥{PASS_SCORE}/10）: **{passed}/{len(all_scores)}問（{passed / len(all_scores):.1%}）**"
        f" / 平均 {statistics.mean(all_scores):.2f} / 中央値 {statistics.median(all_scores)}",
        "",
        "| カテゴリ | 合格率 | 平均 |",
        "|---|---|---|",
        *(
            f"| {category} | {sum(1 for s in values if s >= PASS_SCORE)}/{len(values)} | {statistics.mean(values):.2f} |"
            for category, values in sorted(by_category.items())
        ),
        "",
        "## 不合格の問（分類つき）",
        "",
    ]
    for qid in questions:
        score_record = scores[qid]
        if int(score_record["score"]) >= PASS_SCORE:  # type: ignore[arg-type]
            continue
        lines.append(
            f"- **{qid}**（{score_record['score']}/10）: {score_record['rationale']}"
        )
    lines.append("")
    lines.append("## 全問の裁定")
    for qid, question in questions.items():
        answer = answers[qid]["answer"]  # type: ignore[index]
        score_record = scores[qid]
        verdict = "✅" if int(score_record["score"]) >= PASS_SCORE else "❌"  # type: ignore[arg-type]
        lines += [
            "",
            f"### {qid} {verdict} {score_record['score']}/10",
            f"**Q:** {question['question']}",
            "",
            f"**裁定:** {answer['conclusion']}",  # type: ignore[index]
            "",
            f"**根拠:** {answer['explanation']}",  # type: ignore[index]
            "",
            f"**引用:** {', '.join(answer['rules_cited'])}",  # type: ignore[index]
            "",
            f"**期待結論（golden）:** {question['expected_answer']['conclusion']}",  # type: ignore[index]
            "",
            f"**採点根拠:** {score_record['rationale']}",
        ]
        if score_record.get("dataset_issue"):
            lines.append(f"**dataset要修正候補:** {score_record['dataset_issue']}")

    out = REPO_ROOT / "evaluation" / "reports" / "generation-eval.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"report -> {out.relative_to(REPO_ROOT)}")
    print(f"合格 {passed}/{len(all_scores)}（{passed / len(all_scores):.1%}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
