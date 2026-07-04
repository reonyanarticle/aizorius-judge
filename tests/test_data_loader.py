"""data_loader の単体テスト（インデックス構築の判定ロジックと用語集ロード）。

ChromaDB・Embeddingモデルは使わない純粋ロジックのみ（重い構築は local_index の回帰
テストと scripts/eval_retrieval.py が担う）。
"""

from __future__ import annotations

import json
from pathlib import Path

from aizorius_judge.data_loader import (
    GLOSSARY_SECTION_MAX_PARENTS,
    _is_reusable,
    _source_fingerprint,
    load_glossary_terms,
)


class _FakeCollection:
    def __init__(self, metadata: dict[str, str], count: int) -> None:
        self.metadata = metadata
        self._count = count

    def count(self) -> int:
        return self._count


def test_is_reusable_requires_fingerprint_and_count() -> None:
    good = _FakeCollection({"fingerprint": "fp"}, 10)
    assert _is_reusable(good, "fp", 10)  # type: ignore[arg-type]
    assert not _is_reusable(None, "fp", 10)
    assert not _is_reusable(_FakeCollection({"fingerprint": "old"}, 10), "fp", 10)  # type: ignore[arg-type]
    assert not _is_reusable(_FakeCollection({"fingerprint": "fp"}, 9), "fp", 10)  # type: ignore[arg-type]


def test_source_fingerprint_tracks_hashes_and_model(tmp_path: Path) -> None:
    manifest = {"sources": {"cr_en": {"sha256": "aaa"}, "cr_ja": {"sha256": "bbb"}}}
    (tmp_path / "MANIFEST.json").write_text(json.dumps(manifest))
    fp = _source_fingerprint(tmp_path, "model-x")
    assert "aaa" in fp and "bbb" in fp and fp.endswith("model-x")
    manifest["sources"]["cr_en"]["sha256"] = "ccc"
    (tmp_path / "MANIFEST.json").write_text(json.dumps(manifest))
    assert _source_fingerprint(tmp_path, "model-x") != fp  # CR版が変われば指紋も変わる


def _write_glossary(tmp_path: Path, entries: list[dict[str, object]]) -> None:
    (tmp_path / "glossary.json").write_text(
        json.dumps(entries, ensure_ascii=False), encoding="utf-8"
    )


def test_load_glossary_terms_filters_unknown_and_sorts_by_length(
    tmp_path: Path,
) -> None:
    _write_glossary(
        tmp_path,
        [
            {
                "term_en": "Menace",
                "term_ja": "威迫",
                "rules": ["702.111", "999.9"],
                "sections": [],
            },
            {
                "term_en": "Trample Over Planeswalkers",
                "term_ja": "プレインズウォーカー越えトランプル",
                "rules": ["702.19i"],
                "sections": [],
            },
        ],
    )
    explicit, section = load_glossary_terms(tmp_path, {"702.111", "702.19i"})
    terms = dict(explicit)
    assert terms["威迫"] == ["702.111"]  # 実在しない 999.9 は除外される
    keys = [key for key, _ in explicit]
    # 長い用語が先（「プレインズウォーカー越えトランプル」が「威迫」より先に照合される）
    assert keys.index("プレインズウォーカー越えトランプル") < keys.index("威迫")
    assert section == []


def test_load_glossary_terms_section_expansion_respects_cap(tmp_path: Path) -> None:
    small = [f"500.{i}" for i in range(1, 4)]  # 3親 → 展開される
    big = [
        f"600.{i}" for i in range(1, GLOSSARY_SECTION_MAX_PARENTS + 3)
    ]  # 上限超 → 除外
    _write_glossary(
        tmp_path,
        [
            {
                "term_en": "Turn Structure",
                "term_ja": "ターン構造",
                "rules": [],
                "sections": ["500", "600"],
            }
        ],
    )
    _, section_terms = load_glossary_terms(tmp_path, set(small) | set(big))
    expanded = dict(section_terms)["ターン構造"]
    assert expanded == small  # 大きな章（600）は展開されない


def test_load_glossary_terms_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_glossary_terms(tmp_path, {"100.1"}) == ([], [])
