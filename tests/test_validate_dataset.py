"""scripts/validate_dataset.py の検査ロジック自体のテスト。

dataset品質ゲートの自己検証——subset検査（cited⊆relevant / must⊆cited）や
番号実在チェックが壊れても気づけるようにする。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from validate_dataset import validate_file  # type: ignore # noqa: E402

KNOWN = {"100.1", "100.2", "200.1"}


def _question(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "basic_rules-001",
        "category": "basic_rules",
        "question": "テスト質問",
        "expected_tools": ["search_rules"],
        "expected_answer": {
            "conclusion": "結論",
            "rules_cited": ["100.1"],
            "key_facts": ["事実"],
        },
        "retrieval_relevant_rules": ["100.1", "100.2"],
        "evaluation_criteria": {
            "must_cite_rules": ["100.1"],
            "forbidden_mistakes": ["誤り"],
        },
        "source": "CR test (en)",
    }
    base.update(overrides)
    return base


def _write(tmp_path: Path, questions: list[dict[str, object]]) -> Path:
    path = tmp_path / "dataset.jsonl"
    path.write_text(
        "\n".join(json.dumps(q, ensure_ascii=False) for q in questions) + "\n",
        encoding="utf-8",
    )
    return path


def test_valid_question_passes(tmp_path: Path) -> None:
    assert validate_file(_write(tmp_path, [_question()]), KNOWN) == []


def test_detects_unknown_rule_number(tmp_path: Path) -> None:
    bad = _question(retrieval_relevant_rules=["100.1", "999.9"])
    problems = validate_file(_write(tmp_path, [bad]), KNOWN)
    assert any("999.9" in p for p in problems)


def test_detects_cited_not_subset_of_relevant(tmp_path: Path) -> None:
    bad = _question(
        expected_answer={
            "conclusion": "結論",
            "rules_cited": ["200.1"],  # relevant に無い
            "key_facts": ["事実"],
        },
        evaluation_criteria={"must_cite_rules": ["200.1"], "forbidden_mistakes": []},
    )
    problems = validate_file(_write(tmp_path, [bad]), KNOWN)
    assert problems


def test_detects_must_not_subset_of_cited(tmp_path: Path) -> None:
    bad = _question(
        evaluation_criteria={"must_cite_rules": ["100.2"], "forbidden_mistakes": []}
    )
    problems = validate_file(_write(tmp_path, [bad]), KNOWN)
    assert problems


def test_detects_duplicate_ids(tmp_path: Path) -> None:
    problems = validate_file(_write(tmp_path, [_question(), _question()]), KNOWN)
    assert any("重複" in p for p in problems)


def test_detects_unknown_category_and_tool(tmp_path: Path) -> None:
    bad = _question(category="nonsense", expected_tools=["fake_tool"])
    problems = validate_file(_write(tmp_path, [bad]), KNOWN)
    assert len(problems) >= 2
