"""Hybrid Search（Vector＋BM25 → 融合 → 任意でrerank）。

融合ロジック（RRF・重み付き）は決定論的な純粋関数として分離し、I/O（ChromaDB・
Embedding計算）は `HybridSearcher` に閉じる（Ports & Adapters → .claude/rules/python.md §4）。
ルール番号の直接指定（例 "702.9b"）は検索を介さず正確に引く。
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Sequence

from chromadb.api.types import Where

from aizorius_judge.data_loader import SearchIndex, tokenize
from aizorius_judge.models import CorpusEntry, SearchResult

logger = logging.getLogger(__name__)

__all__ = ["HybridSearcher", "rrf_fuse", "weighted_fuse"]

_RULE_NUMBER_QUERY_RE = re.compile(r"^\s*(\d{3})(?:\.(\d+)([a-z])?)?\.?\s*$")

# 融合前に各系統から取る候補数（融合後に max_results へ絞る）
CANDIDATE_POOL = 50


def rrf_fuse(rankings: Sequence[Sequence[str]], k: int = 60) -> dict[str, float]:
    """Reciprocal Rank Fusion。複数のランキングを 1/(k+rank) の和で融合する（純粋関数）。

    Args:
        rankings: 各検索系統のID列（順位順）。
        k: RRFの定数（標準60）。

    Returns:
        ID→融合スコア（降順ソートは呼び出し側）。
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return scores


def weighted_fuse(
    score_maps: Sequence[dict[str, float]], weights: Sequence[float]
) -> dict[str, float]:
    """min-max正規化した各系統スコアの重み付き和（RRFとの比較用・純粋関数）。"""
    fused: dict[str, float] = {}
    for scores, weight in zip(score_maps, weights, strict=True):
        if not scores:
            continue
        low, high = min(scores.values()), max(scores.values())
        span = (high - low) or 1.0
        for doc_id, score in scores.items():
            normalized = (score - low) / span
            fused[doc_id] = fused.get(doc_id, 0.0) + weight * normalized
    return fused


class HybridSearcher:
    """CRルールの Hybrid Search 本体（依存は SearchIndex として注入）。"""

    def __init__(self, index: SearchIndex, rrf_k: int = 60) -> None:
        self._index = index
        self._rrf_k = rrf_k

    def search(
        self, query: str, max_results: int = 5, section: str | None = None
    ) -> list[SearchResult]:
        """ルールを検索する。

        ルール番号そのものの問い合わせ（例 "702.9b" / "702.9"）は直接引き（前方一致で
        サブルールも返す）、それ以外は Vector＋BM25 → RRF融合で返す。

        Args:
            query: 検索クエリ（日英どちらも可）またはルール番号。
            max_results: 返す最大件数。
            section: 大区分番号（例 "702"）での絞り込み。

        Returns:
            スコア降順の検索結果（該当なしは空リスト。メッセージ整形はツール層の責務）。
        """
        started = time.perf_counter()
        direct = self._direct_number_lookup(query, max_results, section)
        if direct is not None:
            results = direct
        else:
            results = self._hybrid(query, max_results, section)
        took_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "search query=%r section=%r hits=%s took_ms=%.0f",
            query,
            section,
            [r.number for r in results],
            took_ms,
        )
        return results

    def _direct_number_lookup(
        self, query: str, max_results: int, section: str | None
    ) -> list[SearchResult] | None:
        """クエリがルール番号そのものの場合の直接引き。番号でなければ None。"""
        match = _RULE_NUMBER_QUERY_RE.match(query)
        if not match:
            return None
        prefix = match.group(1) + (f".{match.group(2)}" if match.group(2) else "")
        if match.group(3):
            prefix += match.group(3)
        hits = [
            entry
            for entry in self._index.corpus
            if entry.number == prefix or entry.number.startswith(prefix)
        ]
        if section:
            hits = [entry for entry in hits if entry.section == section]
        exact_first = sorted(
            hits, key=lambda entry: (entry.number != prefix, entry.number)
        )
        return [_to_result(entry, 1.0) for entry in exact_first[:max_results]]

    def _hybrid(
        self, query: str, max_results: int, section: str | None
    ) -> list[SearchResult]:
        vector_ranking = self._vector_ranking(query, section)
        bm25_ranking = self._bm25_ranking(query, section)
        fused = rrf_fuse([vector_ranking, bm25_ranking], k=self._rrf_k)
        ranked = [n for n, _ in sorted(fused.items(), key=lambda item: -item[1])]
        if self._index.reranker is not None and len(ranked) > max_results:
            pool = ranked[:CANDIDATE_POOL]
            passages = [self._index.by_number[n].embedding_text() for n in pool]
            order = self._index.reranker.rank(query, passages)
            ranked = [pool[i] for i in order]
            scores = {n: 1.0 / rank for rank, n in enumerate(ranked, start=1)}
        else:
            scores = fused
        return [
            _to_result(self._index.by_number[number], scores[number])
            for number in ranked[:max_results]
        ]

    def _vector_ranking(self, query: str, section: str | None) -> list[str]:
        """言語別ベクトル（number#en / number#ja）を検索し、ルール番号で重複排除して返す。"""
        where: Where | None = {"section": section} if section else None
        result = self._index.collection.query(
            query_embeddings=[self._index.embedder.encode_query(query)],
            n_results=CANDIDATE_POOL
            * 2,  # en/ja 重複排除後に POOL 件残るよう多めに取る
            where=where,
            include=[],
        )
        seen: dict[str, None] = {}
        for vector_id in result["ids"][0]:
            seen.setdefault(vector_id.split("#")[0], None)
        return list(seen)[:CANDIDATE_POOL]

    def _bm25_ranking(self, query: str, section: str | None) -> list[str]:
        scores = self._index.bm25.get_scores(tokenize(query))
        ranked = sorted(
            zip(self._index.corpus, scores, strict=True),
            key=lambda pair: -float(pair[1]),
        )
        if section:
            ranked = [
                (entry, score) for entry, score in ranked if entry.section == section
            ]
        return [entry.number for entry, score in ranked[:CANDIDATE_POOL] if score > 0]


def _to_result(entry: CorpusEntry, score: float) -> SearchResult:
    return SearchResult(
        number=entry.number,
        text_en=entry.text_en,
        text_ja=entry.text_ja,
        section=entry.section,
        category=entry.category,
        score=round(float(score), 6),
    )
