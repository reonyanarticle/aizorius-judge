"""生成層評価の準備：全110問の検索コンテキストを事前計算する。

裁定生成エージェントが各自で重いモデルをロードしなくて済むよう、品質構成＋反復検索
（2クエリunion）の検索結果を JSONL に書き出す。生成の入力を固定することで再現性も担保する。

実行: uv run python scripts/prepare_generation_contexts.py
出力: evaluation/reports/gen-eval/contexts.jsonl（1問=1行）
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from aizorius_judge.data_loader import build_or_load_index
from aizorius_judge.models import RuleGroup
from aizorius_judge.search import HybridSearcher
from aizorius_judge.settings import Settings

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_retrieval import derive_secondary_query, load_questions

REPO_ROOT = Path(__file__).resolve().parent.parent
MAX_RULE_CHARS = 600


def render_group(group: RuleGroup) -> dict[str, object]:
    return {
        "parent": group.parent_number,
        "category": group.category,
        "rules": [
            {
                "number": rule.number,
                "text_ja": (rule.text_ja or "")[:MAX_RULE_CHARS] or None,
                "text_en": rule.text_en[:MAX_RULE_CHARS],
            }
            for rule in group.rules
        ],
    }


def main() -> int:
    logging.basicConfig(level=logging.WARNING)
    searcher = HybridSearcher(build_or_load_index(Settings()))
    questions = load_questions()
    out_dir = REPO_ROOT / "evaluation" / "reports" / "gen-eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "contexts.jsonl"

    with out_path.open("w", encoding="utf-8") as out:
        for question in questions:
            text = str(question["question"])
            groups = {g.parent_number: g for g in searcher.search(text, max_groups=7)}
            secondary = derive_secondary_query(searcher, text)
            queries = [text] + ([secondary] if secondary else [])
            if secondary:
                for group in searcher.search(secondary, max_groups=7):
                    groups.setdefault(group.parent_number, group)
            record = {
                "id": question["id"],
                "category": question["category"],
                "question": text,
                "queries": queries,
                "groups": [render_group(g) for g in groups.values()],
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(question["id"], "->", list(groups))
    print(f"contexts -> {out_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
