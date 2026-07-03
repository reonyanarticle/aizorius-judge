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
    results = searcher.search("702.9b")
    assert results and results[0].number == "702.9b"


@pytest.mark.local_index
def test_rule_number_prefix_returns_subrules(searcher) -> None:
    numbers = [r.number for r in searcher.search("702.9", max_results=5)]
    assert "702.9" in numbers[0]
    assert any(n.startswith("702.9") and n != "702.9" for n in numbers)


@pytest.mark.local_index
def test_japanese_query_finds_flying(searcher) -> None:
    numbers = [
        r.number
        for r in searcher.search("飛行を持つクリーチャーはどうブロックされる？")
    ]
    assert any(n.startswith("702.9") for n in numbers)


@pytest.mark.local_index
def test_section_filter(searcher) -> None:
    results = searcher.search("ブロック", section="509")
    assert results and all(r.section == "509" for r in results)


@pytest.mark.local_index
def test_recall_regression(searcher) -> None:
    """検索品質の回帰ゲート（EVALUATION.md 第1層・高速構成で計測）。

    しきい値は**達成済みの実力の少し下**に置く回帰検知であり、目標値ではない。
    高速構成の実測（recall@5=0.429 / must_cite@5=0.636 / MRR=0.607）に対し
    0.40 / 0.60 / 0.57 をゲートとする。品質構成（rerankあり・must_cite 0.805）の
    計測は scripts/eval_retrieval.py（毎コミットには重すぎるため）。
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from eval_retrieval import evaluate  # type: ignore[import-not-found]

    metrics = evaluate(searcher, k=5)
    assert metrics["recall@5"] >= 0.40, f"recall@5 回帰: {metrics['recall@5']:.3f}"
    assert (
        metrics["must_cite_recall@5"] >= 0.60
    ), f"must_cite recall@5 回帰: {metrics['must_cite_recall@5']:.3f}"
    assert metrics["mrr"] >= 0.57, f"MRR 回帰: {metrics['mrr']:.3f}"
