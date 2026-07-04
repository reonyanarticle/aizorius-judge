"""評価データセットの機械検証。

スキーマ（models.DatasetQuestion）・ID/設問の重複・ルール番号の実在（英語CRの版に対して）を
検査する。内容の正しさ（結論の妥当性）は検査しない——それは出典検証と人間承認の仕事。

データセットは JSONL（1問=1行）。実行: uv run python scripts/validate_dataset.py <dataset.jsonl ...>
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from pydantic import ValidationError

from aizorius_judge.models import DatasetQuestion

REPO_ROOT = Path(__file__).resolve().parent.parent
VALID_TOOLS = {"search_rules", "lookup_card", "get_card_rulings"}
VALID_CATEGORIES = {
    "basic_rules",
    "stack_priority",
    "combat",
    "keywords",
    "commander",
    "layers",
    "replacement_effects",
    "card_interactions",
}


def load_known_rule_numbers() -> set[str]:
    """パース済み英語CRから実在するルール番号の集合を得る。"""
    path = REPO_ROOT / "data" / "comprehensive_rules_en.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    return {rule["number"] for rule in document["rules"]}


def load_jsonl(path: Path) -> tuple[list[dict[str, object]], list[str]]:
    """JSONL（1問=1行）を読み、(レコード, 行単位のエラー) を返す。"""
    records: list[dict[str, object]] = []
    errors: list[str] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as error:
            errors.append(f"{path}:{line_number}: JSONとして読めない: {error}")
    return records, errors


def validate_file(path: Path, known_numbers: set[str]) -> list[str]:
    """1ファイルを検証し、問題点のリストを返す（空なら合格）。"""
    raw, problems = load_jsonl(path)

    questions: list[DatasetQuestion] = []
    for index, item in enumerate(raw):
        try:
            questions.append(DatasetQuestion.model_validate(item))
        except ValidationError as error:
            problems.append(
                f"{path}[{index}]: スキーマ違反: {error.errors()[0]['msg']}"
            )

    for duplicated_id, count in Counter(q.id for q in questions).items():
        if count > 1:
            problems.append(f"id重複: {duplicated_id} ×{count}")
    for duplicated_q, count in Counter(q.question for q in questions).items():
        if count > 1:
            problems.append(f"設問重複: {duplicated_q[:40]}… ×{count}")

    for question in questions:
        if question.category not in VALID_CATEGORIES:
            problems.append(f"{question.id}: 不明なカテゴリ {question.category}")
        if unknown_tools := set(question.expected_tools) - VALID_TOOLS:
            problems.append(f"{question.id}: 不明なツール {sorted(unknown_tools)}")
        cited = set(question.expected_answer.rules_cited)
        relevant = set(question.retrieval_relevant_rules)
        must = set(question.evaluation_criteria.must_cite_rules)
        if not cited <= relevant:
            problems.append(
                f"{question.id}: rules_cited ⊄ retrieval_relevant_rules: {sorted(cited - relevant)}"
            )
        if not must <= cited:
            problems.append(
                f"{question.id}: must_cite_rules ⊄ rules_cited: {sorted(must - cited)}"
            )
        for number in sorted(cited | relevant):
            # セクション参照（"903" 等）はルール番号でなく非許容。個別番号のみ許す
            if number not in known_numbers:
                problems.append(f"{question.id}: CRに存在しない番号 {number}")
    return problems


def main() -> int:
    paths = [Path(arg) for arg in sys.argv[1:]] or [
        REPO_ROOT / "evaluation" / "dataset.jsonl"
    ]
    known_numbers = load_known_rule_numbers()
    exit_code = 0
    for path in paths:
        problems = validate_file(path, known_numbers)
        count = len(load_jsonl(path)[0]) if path.exists() else 0
        if problems:
            exit_code = 1
            print(f"FAIL {path}（{count}問, 問題 {len(problems)}件）")
            for problem in problems:
                print(f"  - {problem}")
        else:
            print(f"PASS {path}（{count}問）")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
