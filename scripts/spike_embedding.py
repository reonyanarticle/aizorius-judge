"""Embeddingモデルの bake-off スパイク（Phase 0）。

候補モデル × インデックス言語戦略ごとに、golden dataset の日本語クエリで
recall@5 / hit@5 を測り、Phase 1 で使うモデルと言語戦略を決める材料を出す。
Vector検索のみの粗い比較であり、BM25・RRF・rerank は Phase 1 で評価する。

実行: uv run python scripts/spike_embedding.py
出力: 標準出力の表 + evaluation/reports/spike-embedding.md
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
TOP_K = 5

# モデル名 -> (query接頭辞, passage接頭辞)。E5系は接頭辞が必須
MODELS: dict[str, tuple[str, str]] = {
    "paraphrase-multilingual-MiniLM-L12-v2": ("", ""),
    "intfloat/multilingual-e5-small": ("query: ", "passage: "),
    "intfloat/multilingual-e5-base": ("query: ", "passage: "),
}


def load_rules(language: str) -> dict[str, str]:
    path = REPO_ROOT / "data" / f"comprehensive_rules_{language}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    return {rule["number"]: rule["text"] for rule in document["rules"]}


def load_queries() -> list[tuple[str, set[str]]]:
    path = REPO_ROOT / "evaluation" / "dataset.jsonl"
    questions = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return [(q["question"], set(q["retrieval_relevant_rules"])) for q in questions]


def build_corpora() -> dict[str, tuple[list[str], list[str]]]:
    """インデックス言語戦略ごとの (ルール番号列, テキスト列) を返す。"""
    rules_en = load_rules("en")
    rules_ja = load_rules("ja")
    numbers = sorted(rules_en)
    en_texts = [f"{n} {rules_en[n]}" for n in numbers]
    both_texts = [
        f"{n} {rules_en[n]}" + (f"\n{rules_ja[n]}" if n in rules_ja else "")
        for n in numbers
    ]
    return {"en": (numbers, en_texts), "en+ja": (numbers, both_texts)}


def evaluate(
    model: SentenceTransformer,
    prefixes: tuple[str, str],
    numbers: list[str],
    texts: list[str],
    queries: list[tuple[str, set[str]]],
) -> dict[str, Any]:
    query_prefix, passage_prefix = prefixes
    started = time.perf_counter()
    corpus_vectors = model.encode(
        [passage_prefix + t for t in texts],
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    index_seconds = time.perf_counter() - started
    query_vectors = model.encode(
        [query_prefix + q for q, _ in queries],
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    similarities = np.asarray(query_vectors) @ np.asarray(corpus_vectors).T

    recalls: list[float] = []
    hits: list[float] = []
    for (_, relevant), row in zip(queries, similarities, strict=True):
        top_numbers = {numbers[i] for i in np.argsort(-row)[:TOP_K]}
        found = len(relevant & top_numbers)
        recalls.append(found / len(relevant))
        hits.append(1.0 if found else 0.0)
    return {
        "recall@5": float(np.mean(recalls)),
        "hit@5": float(np.mean(hits)),
        "index_seconds": round(index_seconds, 1),
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    queries = load_queries()
    corpora = build_corpora()
    logger.info("queries=%d corpus=%d rules", len(queries), len(corpora["en"][0]))

    rows: list[str] = []
    for model_name, prefixes in MODELS.items():
        logger.info("loading %s", model_name)
        model = SentenceTransformer(model_name)
        for corpus_name, (numbers, texts) in corpora.items():
            result = evaluate(model, prefixes, numbers, texts, queries)
            logger.info("%s / %s -> %s", model_name, corpus_name, result)
            rows.append(
                f"| {model_name} | {corpus_name} | {result['recall@5']:.3f} "
                f"| {result['hit@5']:.3f} | {result['index_seconds']}s |"
            )

    report = "\n".join(
        [
            "# Embedding bake-off（Phase 0 スパイク）",
            "",
            f"- クエリ: golden dataset {len(queries)}問（日本語）",
            f"- コーパス: 英語CR全ルール（en）／英語＋日本語連結（en+ja）、{len(corpora['en'][0])}件",
            "- 指標: recall@5（retrieval_relevant_rules に対する再現率）・hit@5（1件以上ヒット）",
            "- Vector検索のみの比較。BM25・RRF・rerank は Phase 1 で評価する。",
            "",
            "| モデル | コーパス | recall@5 | hit@5 | index時間 |",
            "|---|---|---|---|---|",
            *rows,
        ]
    )
    out_path = REPO_ROOT / "evaluation" / "reports" / "spike-embedding.md"
    out_path.write_text(report + "\n", encoding="utf-8")
    logger.info("report -> %s", out_path.relative_to(REPO_ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
