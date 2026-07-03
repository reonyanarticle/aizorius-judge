"""Hybrid Search（Vector＋BM25＋用語集 → RRF融合 → rerank → 親ルールでグループ化）。

融合ロジック（RRF・重み付き）とグループ化は決定論的な純粋関数として分離し、
I/O（ChromaDB・Embedding計算）は `HybridSearcher` に閉じる（Ports & Adapters）。

設計（Phase 1 のエラー分析に基づく）:
- 第3系統として **用語集照合**（クエリ中のMTG用語→定義ルール番号。決定論・LLM不使用）。
- 返却単位は **親ルールのまとまり（RuleGroup）**。正解ルールは兄弟サブルールの
  クラスタで現れることが多く、ジャッジの実務（702.11全体を読む）とも一致する。
- ルール番号の直接指定（例 "702.9b"）は検索を介さず正確に引く。
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Sequence

from chromadb.api.types import Where

from aizorius_judge.data_loader import SearchIndex, tokenize
from aizorius_judge.models import CorpusEntry, RuleGroup, SearchResult

logger = logging.getLogger(__name__)

__all__ = [
    "HybridSearcher",
    "group_by_parent",
    "parent_of",
    "rrf_fuse",
    "weighted_fuse",
]

_RULE_NUMBER_QUERY_RE = re.compile(r"^\s*(\d{3})(?:\.(\d+)([a-z])?)?\.?\s*$")
_PARENT_RE = re.compile(r"^(\d{3}\.\d+)[a-z]$")

# 融合前に各系統から取る候補数（融合・rerank後にグループ化して絞る）
CANDIDATE_POOL = 50


def parent_of(number: str) -> str:
    """サブルール番号の親ルール番号を返す（"702.9b"→"702.9"。親自身はそのまま）。"""
    match = _PARENT_RE.match(number)
    return match.group(1) if match else number


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


def group_by_parent(
    ranked_numbers: Sequence[str],
    scores: dict[str, float],
    corpus_by_parent: dict[str, list[CorpusEntry]],
    max_groups: int,
) -> list[RuleGroup]:
    """ランキング済みのルール番号列を親ルール単位のグループに畳む（純粋関数）。

    グループの順位は「そのグループで最初にヒットした番号のランキング順」。
    グループには親＋全サブルールを番号順で含め、ヒット番号を matched に記録する。
    """
    ordered_parents: list[str] = []
    matched: dict[str, list[str]] = {}
    for number in ranked_numbers:
        parent = parent_of(number)
        if parent not in matched:
            if len(ordered_parents) >= max_groups:
                continue
            ordered_parents.append(parent)
            matched[parent] = []
        if parent in matched:
            matched[parent].append(number)

    groups: list[RuleGroup] = []
    for parent in ordered_parents:
        members = corpus_by_parent.get(parent, [])
        if not members:
            continue
        best_score = max(scores.get(n, 0.0) for n in matched[parent])
        groups.append(
            RuleGroup(
                parent_number=parent,
                category=members[0].category,
                rules=[
                    _to_result(entry, scores.get(entry.number, 0.0))
                    for entry in members
                ],
                matched=matched[parent],
                score=round(float(best_score), 6),
            )
        )
    return groups


class HybridSearcher:
    """CRルールの Hybrid Search 本体（依存は SearchIndex として注入）。"""

    def __init__(self, index: SearchIndex, rrf_k: int = 60) -> None:
        self._index = index
        self._rrf_k = rrf_k
        self._corpus_by_parent: dict[str, list[CorpusEntry]] = {}
        for entry in index.corpus:
            self._corpus_by_parent.setdefault(parent_of(entry.number), []).append(entry)

    def search(
        self, query: str, max_groups: int = 5, section: str | None = None
    ) -> list[RuleGroup]:
        """ルールを検索し、親ルール単位のグループで返す。

        ルール番号そのものの問い合わせ（例 "702.9b" / "702.9"）は直接引き、
        それ以外は Vector＋BM25＋用語集 → RRF融合 →（設定時）rerank。

        Args:
            query: 検索クエリ（日英どちらも可）またはルール番号。
            max_groups: 返す最大グループ数。
            section: 大区分番号（例 "702"）での絞り込み。

        Returns:
            スコア降順のルールグループ（該当なしは空リスト。メッセージ整形はツール層の責務）。
        """
        started = time.perf_counter()
        direct = self._direct_number_lookup(query, max_groups, section)
        groups = (
            direct if direct is not None else self._hybrid(query, max_groups, section)
        )
        took_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "search query=%r section=%r groups=%s took_ms=%.0f",
            query,
            section,
            [g.parent_number for g in groups],
            took_ms,
        )
        return groups

    def _direct_number_lookup(
        self, query: str, max_groups: int, section: str | None
    ) -> list[RuleGroup] | None:
        """クエリがルール番号そのものの場合の直接引き。番号でなければ None。"""
        match = _RULE_NUMBER_QUERY_RE.match(query)
        if not match:
            return None
        prefix = match.group(1) + (f".{match.group(2)}" if match.group(2) else "")
        if match.group(3):
            prefix += match.group(3)
        hits = [
            entry.number
            for entry in self._index.corpus
            if entry.number == prefix or entry.number.startswith(prefix)
        ]
        if section:
            hits = [n for n in hits if self._index.by_number[n].section == section]
        hits.sort(key=lambda n: (n != prefix, n))
        scores = {n: 1.0 for n in hits}
        return group_by_parent(hits, scores, self._corpus_by_parent, max_groups)

    def _hybrid(
        self, query: str, max_groups: int, section: str | None
    ) -> list[RuleGroup]:
        rankings = [
            self._vector_ranking(query, section),
            self._bm25_ranking(query, section),
        ]
        glossary_ranking = self._glossary_ranking(query, section)
        if glossary_ranking:
            rankings.append(glossary_ranking)
        fused = rrf_fuse(rankings, k=self._rrf_k)
        ranked = [n for n, _ in sorted(fused.items(), key=lambda item: -item[1])]
        scores = fused
        if self._index.reranker is not None and ranked:
            pool = ranked[:CANDIDATE_POOL]
            passages = [self._index.by_number[n].embedding_text() for n in pool]
            order = self._index.reranker.rank(query, passages)
            ranked = [pool[i] for i in order]
            scores = {n: 1.0 / rank for rank, n in enumerate(ranked, start=1)}
        return group_by_parent(ranked, scores, self._corpus_by_parent, max_groups)

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

    def _glossary_ranking(self, query: str, section: str | None) -> list[str]:
        """クエリに含まれるMTG用語を用語集と照合し、定義ルール番号を返す（決定論）。

        用語は長い順に照合する（「プレインズウォーカー越えトランプル」が「トランプル」より
        先に当たるように）。同じルール番号は最初の（=最も特異的な）用語の位置で採用。
        """
        query_lower = query.lower()
        ranking: list[str] = []
        for term, rules in self._index.glossary_terms:
            if term not in query_lower:
                continue
            for number in rules:
                if section and self._index.by_number[number].section != section:
                    continue
                if number not in ranking:
                    ranking.append(number)
        return ranking


def _to_result(entry: CorpusEntry, score: float) -> SearchResult:
    return SearchResult(
        number=entry.number,
        text_en=entry.text_en,
        text_ja=entry.text_ja,
        section=entry.section,
        category=entry.category,
        score=round(float(score), 6),
    )
