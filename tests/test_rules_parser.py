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
