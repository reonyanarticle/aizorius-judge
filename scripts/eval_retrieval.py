"""検索単体評価（EVALUATION.md 第1層）：recall@5 / MRR を dataset 全問で測る。

実行: uv run python scripts/eval_retrieval.py [--k 5] [--report]
`--report` で evaluation/reports/retrieval-eval.md に結果を書く。
チューニング比較（融合方式・rerank等）にも使う。
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
import time
from pathlib import Path

from aizorius_judge.data_loader import build_or_load_index
from aizorius_judge.search import HybridSearcher
from aizorius_judge.settings import Settings

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_questions() -> list[dict[str, object]]:
    path = REPO_ROOT / "evaluation" / "dataset.jsonl"
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def evaluate(searcher: HybridSearcher, k: int) -> dict[str, object]:
    """dataset 全問で recall@k（完全集合）／must_cite recall@k（裁定の核）／MRR／レイテンシを測る。"""
    questions = load_questions()
    recalls: list[float] = []
    must_recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    latencies: list[float] = []
    per_category: dict[str, list[float]] = {}
    misses: list[tuple[str, list[str], list[str]]] = []

    for question in questions:
        relevant = set(question["retrieval_relevant_rules"])  # type: ignore[arg-type]
        must = set(question["evaluation_criteria"]["must_cite_rules"])  # type: ignore[index]
        started = time.perf_counter()
        results = searcher.search(str(question["question"]), max_results=k)
        latencies.append((time.perf_counter() - started) * 1000)
        got = [r.number for r in results]
        found = relevant & set(got)
        recall = len(found) / len(relevant)
        recalls.append(recall)
        must_recalls.append(len(must & set(got)) / len(must))
        per_category.setdefault(str(question["category"]), []).append(recall)
        rank = next((i for i, n in enumerate(got, start=1) if n in relevant), 0)
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)
        if recall < 0.5:
            misses.append((str(question["id"]), sorted(relevant), got))

    latencies.sort()
    return {
        "n": len(questions),
        "k": k,
        f"recall@{k}": statistics.mean(recalls),
        f"must_cite_recall@{k}": statistics.mean(must_recalls),
        "mrr": statistics.mean(reciprocal_ranks),
        "p50_ms": latencies[len(latencies) // 2],
        "p95_ms": latencies[int(len(latencies) * 0.95)],
        "per_category": {
            c: statistics.mean(v) for c, v in sorted(per_category.items())
        },
        "misses": misses,
    }


def main() -> int:
    logging.basicConfig(level=logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()

    index = build_or_load_index(Settings())
    searcher = HybridSearcher(index)
    metrics = evaluate(searcher, args.k)

    print(
        f"n={metrics['n']} recall@{args.k}={metrics[f'recall@{args.k}']:.3f} "
        f"must_cite_recall@{args.k}={metrics[f'must_cite_recall@{args.k}']:.3f} "
        f"mrr={metrics['mrr']:.3f}"
    )
    print(f"latency p50={metrics['p50_ms']:.0f}ms p95={metrics['p95_ms']:.0f}ms")
    for category, recall in metrics["per_category"].items():  # type: ignore[union-attr]
        print(f"  {category}: {recall:.3f}")
    print(f"misses(recall<0.5): {len(metrics['misses'])}問")  # type: ignore[arg-type]

    if args.report:
        lines = [
            "# 検索単体評価（第1層）",
            "",
            f"- dataset {metrics['n']}問 / recall@{args.k} **{metrics[f'recall@{args.k}']:.3f}**"
            f" / must_cite recall@{args.k} **{metrics[f'must_cite_recall@{args.k}']:.3f}**"
            f" / MRR {metrics['mrr']:.3f} / p50 {metrics['p50_ms']:.0f}ms / p95 {metrics['p95_ms']:.0f}ms",
            "",
            "| カテゴリ | recall |",
            "|---|---|",
            *(
                f"| {category} | {recall:.3f} |"
                for category, recall in metrics["per_category"].items()  # type: ignore[union-attr]
            ),
            "",
            "## recall<0.5 の問",
            *(
                f"- {qid}: 正解{relevant} → 取得{got}"
                for qid, relevant, got in metrics["misses"]  # type: ignore[misc]
            ),
        ]
        out = REPO_ROOT / "evaluation" / "reports" / "retrieval-eval.md"
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"report -> {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
