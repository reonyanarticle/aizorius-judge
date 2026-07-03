"""検索チューニング実験（Phase 1）：コーパス言語戦略×融合×rerank を一括比較する。

ChromaDBを介さず numpy で直接比較する（実験の反復を速くするため）。
勝った構成を data_loader / search の本実装に反映する。

実行: uv run python scripts/tune_retrieval.py [--rerank]
出力: 標準出力の表 + evaluation/reports/retrieval-tuning.md
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from rank_bm25 import BM25Okapi

from aizorius_judge.data_loader import EmbeddingModel, load_corpus, tokenize
from aizorius_judge.search import rrf_fuse
from aizorius_judge.settings import Settings

REPO_ROOT = Path(__file__).resolve().parent.parent
K = 5
POOL = 50


def load_questions() -> list[tuple[str, set[str], str]]:
    path = REPO_ROOT / "evaluation" / "dataset.jsonl"
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    return [
        (r["question"], set(r["retrieval_relevant_rules"]), r["category"]) for r in rows
    ]


def recall_at_k(
    rankings: list[list[str]], relevant_sets: list[set[str]], k: int
) -> float:
    return statistics.mean(
        len(rel & set(got[:k])) / len(rel)
        for got, rel in zip(rankings, relevant_sets, strict=True)
    )


def mrr(rankings: list[list[str]], relevant_sets: list[set[str]]) -> float:
    values = []
    for got, rel in zip(rankings, relevant_sets, strict=True):
        rank = next((i for i, n in enumerate(got, start=1) if n in rel), 0)
        values.append(1.0 / rank if rank else 0.0)
    return statistics.mean(values)


def vector_rankings(
    query_vectors: NDArray[np.float32],
    passage_vectors: NDArray[np.float32],
    ids: list[str],
    pool: int,
) -> list[list[str]]:
    """cosine（正規化済み内積）で各クエリの上位poolのルール番号を返す。

    ids に同一ルールが複数回現れる場合（言語別ベクトル）は最良スコアで重複排除する。
    """
    sims = query_vectors @ passage_vectors.T
    rankings: list[list[str]] = []
    for row in sims:
        seen: dict[str, None] = {}
        for index in np.argsort(-row):
            number = ids[index]
            if number not in seen:
                seen[number] = None
            if len(seen) >= pool:
                break
        rankings.append(list(seen))
    return rankings


def bm25_rankings(
    corpus_tokens: list[list[str]], ids: list[str], queries: list[str], pool: int
) -> list[list[str]]:
    bm25 = BM25Okapi(corpus_tokens)
    rankings = []
    for query in queries:
        scores = bm25.get_scores(tokenize(query))
        order = np.argsort(-scores)
        rankings.append([ids[i] for i in order[:pool] if scores[i] > 0])
    return rankings


def fuse_rankings(rankings_list: list[list[list[str]]], k: int = 60) -> list[list[str]]:
    fused = []
    for per_query in zip(*rankings_list, strict=True):
        scores = rrf_fuse(list(per_query), k=k)
        fused.append([n for n, _ in sorted(scores.items(), key=lambda item: -item[1])])
    return fused


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rerank", action="store_true", help="bge-reranker-v2-m3 の比較も行う"
    )
    args = parser.parse_args()

    settings = Settings()
    corpus = load_corpus(settings.data_dir)
    questions = load_questions()
    queries = [q for q, _, _ in questions]
    relevant_sets = [r for _, r, _ in questions]
    embedder = EmbeddingModel(settings.embedding_model, settings.embedding_device)

    numbers = [entry.number for entry in corpus]
    en_texts = [f"{e.number} {e.text_en}" for e in corpus]
    ja_texts = [
        f"{e.number} {e.text_ja}" if e.text_ja else f"{e.number} {e.text_en}"
        for e in corpus
    ]
    combined_texts = [e.embedding_text() for e in corpus]

    print("encoding queries / passages…", file=sys.stderr)
    query_vecs = np.asarray(
        [embedder.encode_query(q) for q in queries], dtype=np.float32
    )
    vec = {
        "combined": vector_rankings(
            query_vecs, embedder.encode_passages(combined_texts), numbers, POOL
        ),
        "en": vector_rankings(
            query_vecs, embedder.encode_passages(en_texts), numbers, POOL
        ),
        "ja": vector_rankings(
            query_vecs, embedder.encode_passages(ja_texts), numbers, POOL
        ),
    }
    # dual: en/ja 別ベクトルを同一ID空間に重ねて最良スコアで統合
    dual_vectors = np.concatenate(
        [embedder.encode_passages(en_texts), embedder.encode_passages(ja_texts)]
    )
    vec["dual"] = vector_rankings(query_vecs, dual_vectors, numbers + numbers, POOL)

    bm = {
        "combined": bm25_rankings(
            [tokenize(t) for t in combined_texts], numbers, queries, POOL
        ),
        "ja": bm25_rankings([tokenize(t) for t in ja_texts], numbers, queries, POOL),
    }

    rows: list[tuple[str, float, float]] = []

    def report(name: str, rankings: list[list[str]]) -> None:
        r = recall_at_k(rankings, relevant_sets, K)
        m = mrr(rankings, relevant_sets)
        rows.append((name, r, m))
        print(f"{name:40s} recall@5={r:.3f} mrr={m:.3f}")

    for key, rankings in vec.items():
        report(f"vector[{key}]", rankings)
    for key, rankings in bm.items():
        report(f"bm25[{key}]", rankings)
    report(
        "rrf(vector[combined]+bm25[combined])",
        fuse_rankings([vec["combined"], bm["combined"]]),
    )
    report("rrf(vector[dual]+bm25[ja])", fuse_rankings([vec["dual"], bm["ja"]]))
    report(
        "rrf(vector[dual]+bm25[combined])", fuse_rankings([vec["dual"], bm["combined"]])
    )
    report(
        "rrf(vector[dual]+vector[combined]+bm25[ja])",
        fuse_rankings([vec["dual"], vec["combined"], bm["ja"]]),
    )

    best_base = fuse_rankings([vec["dual"], bm["combined"]])

    if args.rerank:
        from sentence_transformers import CrossEncoder

        print("reranking with BAAI/bge-reranker-v2-m3…", file=sys.stderr)
        by_number = {e.number: e for e in corpus}
        reranker = CrossEncoder("BAAI/bge-reranker-v2-m3", device=embedder.device)
        reranked: list[list[str]] = []
        for query, candidates in zip(queries, best_base, strict=True):
            pool = candidates[:POOL]
            pairs: list[list[str]] = [
                [query, by_number[n].embedding_text()] for n in pool
            ]
            scores = reranker.predict(pairs, show_progress_bar=False)
            order = np.argsort(-np.asarray(scores))
            reranked.append([pool[i] for i in order])
        report("rrf(dual+bm25[combined]) + bge-reranker-v2-m3", reranked)

    out = REPO_ROOT / "evaluation" / "reports" / "retrieval-tuning.md"
    lines: list[Any] = [
        "# 検索チューニング実験（Phase 1）",
        "",
        f"- dataset 110問（日本語クエリ）/ recall@5・MRR / 候補pool={POOL}",
        "",
        "| 構成 | recall@5 | MRR |",
        "|---|---|---|",
        *(f"| {name} | {r:.3f} | {m:.3f} |" for name, r, m in rows),
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"report -> {out.relative_to(REPO_ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
