"""hold-out 口語クエリでの検索汎化測定（dataset 非依存の過学習チェック）。

fetch_holdout_queries.py が取得した実ユーザーの質問（英語・口語）に対して検索を実行し、
採用回答が引用した CR ルール番号（弱ラベル）が返却グループに入る割合を測る。
dataset でのチューニングが hold-out でも通用するか（汎化）の追跡が目的で、
golden dataset の recall とは別物として扱う（弱ラベルは網羅性の保証がない）。

- 旧CR番号（現行コーパスに実在しない番号）はラベルから除外し、除外数を報告する。
  なお「実在するが内容が変わった改番」（例: 優先権が116→117に移動）はラベルノイズとして
  残るため、投稿年別の被覆も出して古い投稿ほど低いか（＝改番ノイズか）を確認する。
- クエリはタイトル（口語の短文）とタイトル＋本文冒頭の2通りで測る。

実行: uv run python scripts/eval_holdout.py [--k 7] [--limit 0]
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
from datetime import UTC
from pathlib import Path

from aizorius_judge.data_loader import build_or_load_index
from aizorius_judge.search import HybridSearcher
from aizorius_judge.settings import Settings

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
HOLDOUT_PATH = REPO_ROOT / "evaluation" / "holdout" / "se-questions.jsonl"


def main() -> int:
    logging.basicConfig(level=logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=7)
    parser.add_argument("--limit", type=int, default=0, help="0=全問")
    parser.add_argument(
        "--file", default=None, help="hold-outファイル名（既定 se-questions.jsonl）"
    )
    args = parser.parse_args()

    global HOLDOUT_PATH
    if args.file:
        HOLDOUT_PATH = HOLDOUT_PATH.parent / args.file
    if not HOLDOUT_PATH.exists():
        print(
            f"{HOLDOUT_PATH} が無い（scripts/fetch_holdout_queries.py で取得する）",
            file=sys.stderr,
        )
        return 1

    index = build_or_load_index(Settings())
    searcher = HybridSearcher(index)
    known = {entry.number for entry in index.corpus}

    records = [
        json.loads(line)
        for line in HOLDOUT_PATH.read_text(encoding="utf-8").splitlines()
    ]
    dropped_obsolete = 0
    cases: list[tuple[str, str, set[str], int]] = []
    for record in records:
        labels = set(record["answer_cited_rules"])
        current = labels & known
        dropped_obsolete += len(labels - current)
        if current:
            year = 1970
            if record.get("creation_date"):
                from datetime import datetime

                year = datetime.fromtimestamp(int(record["creation_date"]), tz=UTC).year
            cases.append((record["title"], record["body"], current, year))
    if args.limit:
        cases = cases[: args.limit]

    for query_name, make_query in (
        ("title", lambda title, body: title),
        ("title+body", lambda title, body: f"{title} {body[:300]}"),
    ):
        coverages: list[float] = []
        by_era: dict[str, list[float]] = {}
        full_hits = 0
        misses: list[tuple[str, set[str]]] = []
        for title, body, labels, year in cases:
            groups = searcher.search(make_query(title, body), max_groups=args.k)
            got = {rule.number for group in groups for rule in group.rules}
            coverage = len(labels & got) / len(labels)
            coverages.append(coverage)
            era = (
                "〜2015"
                if year <= 2015
                else ("2016〜2020" if year <= 2020 else "2021〜")
            )
            by_era.setdefault(era, []).append(coverage)
            if coverage == 1.0:
                full_hits += 1
            elif coverage == 0.0:
                misses.append((title, labels))
        era_text = " ".join(
            f"{era}:{statistics.mean(vals):.3f}(n={len(vals)})"
            for era, vals in sorted(by_era.items())
        )
        print(
            f"[{query_name}] n={len(cases)} "
            f"弱ラベル被覆@{args.k}={statistics.mean(coverages):.3f} "
            f"全ラベル回収={full_hits}/{len(cases)} "
            f"ゼロ回収={len(misses)}問"
        )
        print(f"  年代別: {era_text}")
        for title, labels in misses[:5]:
            print(f"  miss: {sorted(labels)} <- {title[:70]}")
    print(f"（旧CR番号として除外した引用: {dropped_obsolete}件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
