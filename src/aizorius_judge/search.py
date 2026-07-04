"""Hybrid Search（Vector＋BM25＋用語集 → RRF融合 → rerank → 親ルールでグループ化）。

融合ロジック（RRF・重み付き）とグループ化は決定論的な純粋関数として分離し、
I/O（ChromaDB・Embedding計算）は `HybridSearcher` に閉じる（Ports & Adapters）。

設計（検索単体評価のエラー分析に基づく）:
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

from aizorius_judge.data_loader import SearchIndex, normalize_text, tokenize
from aizorius_judge.models import CorpusEntry, RuleGroup, SearchResult

logger = logging.getLogger(__name__)

__all__ = [
    "HybridSearcher",
    "group_by_parent",
    "matches_number_prefix",
    "number_sort_key",
    "parent_of",
    "rrf_fuse",
    "weighted_fuse",
]

_RULE_NUMBER_QUERY_RE = re.compile(r"^\s*(\d{3})(?:\.(\d+)([a-z])?)?\.?\s*$")
_PARENT_RE = re.compile(r"^(\d{3}\.\d+)[a-z]$")
_NUMBER_PARTS_RE = re.compile(r"^(\d{3})(?:\.(\d+)([a-z])?)?$")

# 融合前に各系統から取る候補数（融合・rerank後にグループ化して絞る）
CANDIDATE_POOL = 50
# 用語集セクション展開系統の融合重み（弱い補助。search.py の _hybrid 参照）
GLOSSARY_SECTION_WEIGHT = 0.3


def parent_of(number: str) -> str:
    """サブルール番号の親ルール番号を返す（"702.9b"→"702.9"。親自身はそのまま）。"""
    match = _PARENT_RE.match(number)
    return match.group(1) if match else number


def number_sort_key(number: str) -> tuple[int, int, str]:
    """ルール番号の数値順ソートキー（文字列比較だと "702.10" < "702.2" になるため）。

    形式外の番号は末尾に寄せる（section=999）。
    """
    match = _NUMBER_PARTS_RE.match(number)
    if not match:
        return (999, 999, number)
    section = int(match.group(1))
    sub = int(match.group(2)) if match.group(2) else 0
    return (section, sub, match.group(3) or "")


def matches_number_prefix(number: str, prefix: str) -> bool:
    """ルール番号がプレフィックス問い合わせに該当するか（境界を厳密に判定する）。

    単純な前方一致だと "702.9" に "702.90"〜"702.99" が混入する（CR実データで再現）ため、
    プレフィックスの形に応じて許す続き方を限定する:
    - "702"（セクション）: 完全一致か、直後が "."。
    - "702.9"（親ルール）: 完全一致か、直後が英字1文字（サブルール）。
    - "702.9b"（サブルール）: 完全一致のみ。
    """
    if number == prefix:
        return True
    if not number.startswith(prefix):
        return False
    rest = number[len(prefix) :]
    if "." not in prefix:
        return rest.startswith(".")
    if prefix[-1].isdigit():
        return len(rest) == 1 and rest.isalpha()
    return False


def rrf_fuse(
    rankings: Sequence[Sequence[str]],
    k: int = 60,
    weights: Sequence[float] | None = None,
) -> dict[str, float]:
    """Reciprocal Rank Fusion。複数のランキングを w/(k+rank) の和で融合する（純粋関数）。

    Args:
        rankings: 各検索系統のID列（順位順）。
        k: RRFの定数（標準60）。
        weights: 系統ごとの重み（省略時は全て1.0。弱い補助系統に小さい値を与える）。

    Returns:
        ID→融合スコア（降順ソートは呼び出し側）。
    """
    if weights is None:
        weights = [1.0] * len(rankings)
    scores: dict[str, float] = {}
    for ranking, weight in zip(rankings, weights, strict=True):
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + weight / (k + rank)
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
            if parent not in corpus_by_parent:
                continue  # コーパスに親が無い番号に max_groups の枠を消費させない
            if len(ordered_parents) >= max_groups:
                continue
            ordered_parents.append(parent)
            matched[parent] = []
        matched[parent].append(number)

    groups: list[RuleGroup] = []
    for parent in ordered_parents:
        members = corpus_by_parent[parent]
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

    @property
    def glossary_terms(self) -> list[tuple[str, list[str]]]:
        """照合用語→参照ルール番号の対応（読み取り用）。

        反復検索のキーワード導出（scripts/eval_retrieval.py）など、検索の外側が
        用語対応を参照するための公開アクセサ（内部の SearchIndex に直接触れさせない）。
        """
        return self._index.glossary_terms

    def search(
        self, query: str, max_groups: int = 7, section: str | None = None
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
        """クエリがルール番号そのものの場合の直接引き。番号でなければ None。

        全角の番号（"７０２．９ｂ"）も NFKC 正規化して受け付ける。
        """
        match = _RULE_NUMBER_QUERY_RE.match(normalize_text(query))
        if not match:
            return None
        prefix = match.group(1) + (f".{match.group(2)}" if match.group(2) else "")
        if match.group(3):
            prefix += match.group(3)
        hits = [
            entry.number
            for entry in self._index.corpus
            if matches_number_prefix(entry.number, prefix)
        ]
        if section:
            hits = [n for n in hits if self._index.by_number[n].section == section]
        hits.sort(key=lambda n: (n != prefix, number_sort_key(n)))
        scores = {n: 1.0 for n in hits}
        return group_by_parent(hits, scores, self._corpus_by_parent, max_groups)

    def _hybrid(
        self, query: str, max_groups: int, section: str | None
    ) -> list[RuleGroup]:
        rankings = [
            self._vector_ranking(query, section),
            self._bm25_ranking(query, section),
        ]
        weights = [1.0, 1.0]
        glossary_ranking = self._glossary_ranking(
            query, section, self._index.glossary_terms
        )
        if glossary_ranking:
            rankings.append(glossary_ranking)
            weights.append(1.0)
        # セクション展開は「候補pool（rerank対象）に種を撒く」ための弱い補助系統。
        # rerank無しだと top群を直接押し上げて全指標が悪化する（実測）ため、reranker がある
        # 構成でのみ有効化する
        if self._index.reranker is not None:
            section_ranking = self._glossary_ranking(
                query, section, self._index.glossary_section_terms
            )
            if section_ranking:
                rankings.append(section_ranking)
                weights.append(GLOSSARY_SECTION_WEIGHT)
        fused = rrf_fuse(rankings, k=self._rrf_k, weights=weights)
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

    def _glossary_ranking(
        self, query: str, section: str | None, terms: list[tuple[str, list[str]]]
    ) -> list[str]:
        """クエリに含まれるMTG用語を用語対応表と照合し、ルール番号を返す（決定論）。

        用語は長い順に照合する（「プレインズウォーカー越えトランプル」が「トランプル」より
        先に当たるように）。同じルール番号は最初の（=最も特異的な）用語の位置で採用。
        クエリは NFKC 正規化してから照合する（全角半角ゆれの吸収。用語キー側も正規化済み）。
        """
        query_lower = normalize_text(query)
        ranking: list[str] = []
        for term, rules in terms:
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
