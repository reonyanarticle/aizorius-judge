"""rules_parser の単体テスト。

フィクスチャは合成テキスト（実CRの本文はライセンス上コミットしないため、
構造だけを模した架空のルール文で検証する）。
"""

from __future__ import annotations

from aizorius_judge.rules_parser import extract_lines_from_html, parse_rules_lines

# 実CRと同じ構造の合成フィクスチャ: 目次 → 本文（パート/セクション/ルール/サブルール）→ 用語集
SYNTHETIC_EN = """\
Fake Rules Document

Contents

1. Alpha Concepts

100. General

200. Parts of a Widget

Glossary

Credits

1. Alpha Concepts

100. General

100.1. This is a fake top-level rule.

100.1a This is a fake subrule.

100.1b Another fake subrule. See rule 200.1.

200. Parts of a Widget

200.1. Widgets have parts.

704.5k A fake subrule with letter k.

704.5m Letters l and o are skipped.

Glossary

Fake Term
A term that must not be parsed as a rule.

Credits
"""


def test_parses_rules_and_subrules() -> None:
    rules = parse_rules_lines(SYNTHETIC_EN.splitlines())
    numbers = [rule.number for rule in rules]
    assert numbers == ["100.1", "100.1a", "100.1b", "200.1", "704.5k", "704.5m"]


def test_category_and_section_follow_headings() -> None:
    rules = {rule.number: rule for rule in parse_rules_lines(SYNTHETIC_EN.splitlines())}
    assert rules["100.1"].section == "100"
    assert rules["100.1"].category == "General"
    assert rules["200.1"].category == "Parts of a Widget"


def test_glossary_is_not_ingested() -> None:
    rules = parse_rules_lines(SYNTHETIC_EN.splitlines())
    assert all("Fake Term" not in rule.text for rule in rules)


def test_toc_does_not_produce_rules() -> None:
    # 目次にはセクション見出ししかないので、ルールは本文の6件だけになる
    assert len(parse_rules_lines(SYNTHETIC_EN.splitlines())) == 6


SYNTHETIC_JA_HTML = """\
<html><body>
<script>ignored();</script>
<h5>1. 架空の概念</h5>
<p><strong><a id="r100">100.</a> 原則</strong></p>
<p><a id="r100.1">100.1.</a> これは架空のルールである。<a class="g" href="#g_x">用語</a>を含む。</p>
<p><a id="r100.1a">100.1a</a> これは架空のサブルールである。</p>
<p>用語集</p>
<p>架空の用語: ルールとして取り込まれない。</p>
</body></html>
"""


def test_html_extraction_and_parse() -> None:
    lines = extract_lines_from_html(SYNTHETIC_JA_HTML)
    rules = parse_rules_lines(lines)
    numbers = [rule.number for rule in rules]
    assert numbers == ["100.1", "100.1a"]
    assert rules[0].category == "原則"
    # インラインリンクのテキストは本文に残る
    assert "用語" in rules[0].text
    assert all("架空の用語" not in rule.text for rule in rules)


# --- 用語集パーサ（重大バグの再発防止: 参照抽出の複数形・レター範囲・列挙） ---

from aizorius_judge.rules_parser import (  # noqa: E402
    _referenced_rules,
    merge_glossaries,
    parse_glossary_en,
    parse_glossary_ja,
)


def test_referenced_rules_singular() -> None:
    rules, sections = _referenced_rules("See rule 702.9b.")
    assert rules == ["702.9b"]
    assert sections == []


def test_referenced_rules_plural_letter_range() -> None:
    # "rules 509.1b–c" 形式（複数形＋enダッシュ範囲）を各サブルールに展開する
    rules, _ = _referenced_rules("See rules 509.1b–c.")
    assert rules == ["509.1b", "509.1c"]


def test_referenced_rules_range_skips_l_and_o() -> None:
    # CRはサブルールのレターに l/o を使わない（1/0との混同回避）
    rules, _ = _referenced_rules("See rules 111.10k–m.")
    assert rules == ["111.10k", "111.10m"]


def test_referenced_rules_enumeration() -> None:
    # "rules 613.2, 707.2, and 707.3" の列挙をすべて拾う
    rules, _ = _referenced_rules("See rules 613.2, 707.2, and 707.3.")
    assert rules == ["613.2", "707.2", "707.3"]


def test_referenced_rules_section() -> None:
    _, sections = _referenced_rules('See rule 502, "Untap Step." Also rules 510.')
    assert sections == ["502", "510"]


SYNTHETIC_GLOSSARY_EN = """\
Fake Rules Document

Contents

Glossary

Credits

100. General

100.1. A fake rule.

Glossary

Alpha Term
A term defined by rules 509.1b–c.

Beta Term
See rule 100.1.

Credits

Fake credits line.
"""


def test_parse_glossary_en_blocks_and_refs() -> None:
    entries = parse_glossary_en(SYNTHETIC_GLOSSARY_EN)
    assert [e.term_en for e in entries] == ["Alpha Term", "Beta Term"]
    assert entries[0].rules == ["509.1b", "509.1c"]
    assert entries[1].rules == ["100.1"]


SYNTHETIC_GLOSSARY_JA = (
    '<h5><a id="g_alpha">アルファ用語（あるふぁようご）／Alpha Term</a></h5>'
    "<p>rule 200.1 を参照。</p>"
    '<h5><a id="g_gamma">ガンマ用語（がんまようご）／Gamma Term</a></h5>'
    "<p>日本語側にしかない用語。</p></div>"
)


def test_parse_glossary_ja_terms_and_reading_removed() -> None:
    entries = parse_glossary_ja(SYNTHETIC_GLOSSARY_JA)
    assert [e.term_en for e in entries] == ["Alpha Term", "Gamma Term"]
    assert entries[0].term_ja == "アルファ用語"  # 読み（…）は除去される
    assert entries[0].rules == ["200.1"]


def test_merge_glossaries_en_is_authoritative_ja_supplements() -> None:
    en = parse_glossary_en(SYNTHETIC_GLOSSARY_EN)
    ja = parse_glossary_ja(SYNTHETIC_GLOSSARY_JA)
    merged = merge_glossaries(en, ja)
    by_en = {e.term_en: e for e in merged}
    alpha = by_en["Alpha Term"]
    assert alpha.term_ja == "アルファ用語"
    assert set(alpha.rules) == {"509.1b", "509.1c", "200.1"}  # 日英の参照が合流する
    assert "Gamma Term" in by_en  # 日本語側にしかない用語も残る
