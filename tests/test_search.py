"""検索コアの単体テスト（純粋関数）と検索品質の回帰テスト（要ローカルインデックス）。

- 純粋関数（tokenize / rrf_fuse / weighted_fuse / 番号直接引きの判定）は常に実行される。
- recall@5 の回帰テストは ChromaDB インデックスとCR JSONがあるローカルでのみ実行
  （CIには実データを置かないためスキップ）。
"""

from __future__ import annotations

import pytest

from aizorius_judge.data_loader import tokenize
from aizorius_judge.search import rrf_fuse, weighted_fuse


def test_tokenize_keeps_rule_numbers() -> None:
    tokens = tokenize("Flying 702.9b works")
    assert "702.9b" in tokens
    assert "flying" in tokens


def test_tokenize_japanese_bigrams() -> None:
    tokens = tokenize("飛行を持つ")
    assert "飛行" in tokens  # 「飛行」はバイグラムとして残る
    assert all(len(t) <= 2 or t[0].isascii() for t in tokens)


def test_rrf_fuse_prefers_agreement() -> None:
    # 両系統で上位の "a" が、片系統だけ1位の "b" より高スコアになる
    scores = rrf_fuse([["a", "b", "c"], ["a", "c", "b"]], k=60)
    assert scores["a"] > scores["b"]
    assert scores["a"] > scores["c"]


def test_rrf_fuse_empty() -> None:
    assert rrf_fuse([]) == {}


def test_weighted_fuse_normalizes_scales() -> None:
    # スケールが違ってもmin-max正規化で比較可能になる
    # 系統1: a=1.0, b=0.0（正規化後）／系統2: a=0.0, b=1.0 → 等重みで両者0.5
    fused = weighted_fuse(
        [{"a": 100.0, "b": 0.0}, {"a": 0.9, "b": 1.0}], weights=[0.5, 0.5]
    )
    assert fused["a"] == pytest.approx(0.5)
    assert fused["b"] == pytest.approx(0.5)


@pytest.fixture(scope="module")
def searcher():
    """高速構成（rerankなし）のsearcher。

    回帰テストを毎コミット回せる速度に保つため rerank は外す（品質構成の計測は
    scripts/eval_retrieval.py で行う → docs/EVALUATION.md）。
    """
    from aizorius_judge.data_loader import build_or_load_index
    from aizorius_judge.search import HybridSearcher
    from aizorius_judge.settings import Settings

    settings = Settings()
    settings.reranker_model = None
    if not (settings.data_dir / "comprehensive_rules_en.json").exists():
        pytest.skip(
            "CR JSONが無い（ローカル専用テスト。scripts/fetch_rules.sh → parse_rules.py）"
        )
    return HybridSearcher(build_or_load_index(settings))


@pytest.mark.local_index
def test_direct_rule_number_lookup(searcher) -> None:
    groups = searcher.search("702.9b")
    assert groups and groups[0].parent_number == "702.9"
    assert "702.9b" in groups[0].matched
    assert any(r.number == "702.9b" for r in groups[0].rules)


@pytest.mark.local_index
def test_rule_number_prefix_returns_group_with_subrules(searcher) -> None:
    groups = searcher.search("702.9", max_groups=5)
    numbers = [r.number for r in groups[0].rules]
    assert "702.9" in numbers
    assert any(n.startswith("702.9") and n != "702.9" for n in numbers)


@pytest.mark.local_index
def test_japanese_query_finds_flying(searcher) -> None:
    groups = searcher.search("飛行を持つクリーチャーはどうブロックされる？")
    assert any(g.parent_number.startswith("702.9") for g in groups)


@pytest.mark.local_index
def test_glossary_term_maps_to_rule(searcher) -> None:
    # 用語集系統: 「威迫」→702.111（現行CRの番号。702.11は呪禁）
    groups = searcher.search("威迫は何体でブロックする必要がありますか")
    assert any(g.parent_number.startswith("702.111") for g in groups)


@pytest.mark.local_index
def test_section_filter(searcher) -> None:
    groups = searcher.search("ブロック", section="509")
    assert groups and all(r.section == "509" for g in groups for r in g.rules)


@pytest.mark.local_index
def test_recall_regression(searcher) -> None:
    """検索品質の回帰ゲート（EVALUATION.md 第1層・高速構成・グループ返却で計測）。

    しきい値は**達成済みの実力の少し下**に置く回帰検知であり、目標値ではない。
    しきい値の根拠となる実測値は evaluation/reports/retrieval-eval.md。
    品質構成（rerankあり）の計測は scripts/eval_retrieval.py（毎コミットには重すぎるため）。
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from eval_retrieval import evaluate  # type: ignore[import-not-found]

    metrics = evaluate(searcher, k=5)
    assert metrics["recall@5"] >= 0.60, f"recall@5 回帰: {metrics['recall@5']:.3f}"
    assert (
        metrics["must_cite_recall@5"] >= 0.75
    ), f"must_cite recall@5 回帰: {metrics['must_cite_recall@5']:.3f}"
    assert metrics["mrr"] >= 0.68, f"MRR 回帰: {metrics['mrr']:.3f}"
