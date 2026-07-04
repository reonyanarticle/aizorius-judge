"""生成層評価の準備：dataset 全問の検索コンテキストを事前計算する。

裁定生成エージェントが各自で重いモデルをロードしなくて済むよう、品質構成＋反復検索
（質問文＋用語キーワード＋あれば実LLM言い換え）の検索結果を JSONL に書き出す。
生成の入力を固定することで再現性も担保する。言い換えの生成規約は
evaluation/test_runner.md（golden 遮断・ルール番号禁止）。

実行: uv run python scripts/prepare_generation_contexts.py [--ids id1,id2,...]
出力: evaluation/reports/gen-eval/contexts.jsonl（1問=1行。--ids 指定時は contexts-partial.jsonl）
"""

from __future__ import annotations

import argparse
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
    """RuleGroup を生成エージェント向けのJSON構造に整形する（本文はMAX_RULE_CHARSで切る）。"""
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


def load_rephrasings() -> dict[str, list[str]]:
    """実LLM生成の言い換えクエリを読む（無ければ空。生成手順は test_runner.md）。"""
    path = REPO_ROOT / "evaluation" / "reports" / "gen-eval" / "rephrasings.jsonl"
    if not path.exists():
        return {}
    result: dict[str, list[str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        result[str(item["id"])] = [str(q) for q in item["queries"]]
    return result


def main() -> int:
    """dataset全問（または--idsの問）の検索コンテキストを書き出す。"""
    logging.basicConfig(level=logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ids", default=None, help="カンマ区切りの問ID（指定時は部分再生成）"
    )
    args = parser.parse_args()
    only_ids = set(args.ids.split(",")) if args.ids else None

    searcher = HybridSearcher(build_or_load_index(Settings()))
    questions = load_questions()
    if only_ids:
        questions = [q for q in questions if str(q["id"]) in only_ids]
    rephrasings = load_rephrasings()
    out_dir = REPO_ROOT / "evaluation" / "reports" / "gen-eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / ("contexts-partial.jsonl" if only_ids else "contexts.jsonl")

    with out_path.open("w", encoding="utf-8") as out:
        for question in questions:
            text = str(question["question"])
            groups = {g.parent_number: g for g in searcher.search(text, max_groups=7)}
            secondary = derive_secondary_query(searcher, text)
            queries = [text] + ([secondary] if secondary else [])
            queries += rephrasings.get(str(question["id"]), [])
            for extra in queries[1:]:
                for group in searcher.search(extra, max_groups=7):
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
