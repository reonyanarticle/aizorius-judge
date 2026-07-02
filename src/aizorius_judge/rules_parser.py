"""総合ルール（CR）原文のパース。

英語CR（プレーンテキスト）と日本語CR（mtg-jp.comのHTML）を、共通の行ベース形式に
正規化してから `RuleEntry` の配列に変換する。LLMは使わない（決定論的な文字列処理のみ）。

CR原文の構造（両言語共通）:
- パート見出し「1. Game Concepts」、セクション見出し「100. General」
- ルール行「100.1. 本文」、サブルール行「100.1a 本文」（サブルールは番号直後にピリオドなし）
- 冒頭に目次（セクション見出しと同形式の行）があり、本文の後に用語集・クレジットが続く
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from html.parser import HTMLParser

from aizorius_judge.models import RuleEntry

__all__ = ["extract_lines_from_html", "parse_rules_lines"]

_SECTION_RE = re.compile(r"^(\d{3})\.\s+(.+)$")
_RULE_RE = re.compile(r"^(\d{3})\.(\d+[a-z]?)\.?\s+(.+)$")
_GLOSSARY_TITLES = ("Glossary", "用語集")


def parse_rules_lines(lines: Sequence[str]) -> list[RuleEntry]:
    """正規化済みの行リストからルールを抽出する。

    目次にはセクション見出ししか現れない（個別ルール行は本文にしかない）ため、
    見出しは出現のたびに現在のセクション/カテゴリとして上書きすれば、ルール行の
    直前に見た見出し＝本文の見出しになる。ルールを1件以上読んだあとに用語集の
    見出しに達したら打ち切る（用語集・クレジットを取り込まない）。

    Args:
        lines: CR本文の行（英語TXTの行、またはHTMLから抽出した行）。

    Returns:
        文書順の `RuleEntry` 配列。
    """
    rules: list[RuleEntry] = []
    category = ""
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if line in _GLOSSARY_TITLES and rules:
            break
        rule_match = _RULE_RE.match(line)
        if rule_match:
            section, sub, text = rule_match.groups()
            rules.append(
                RuleEntry(
                    number=f"{section}.{sub}",
                    text=text.strip(),
                    section=section,
                    category=category,
                )
            )
            continue
        section_match = _SECTION_RE.match(line)
        if section_match:
            category = section_match.group(2).strip()
    return rules


class _ParagraphExtractor(HTMLParser):
    """HTMLから段落・見出し単位のテキスト行を抽出する（mtg-jp.comの総合ルールページ用）。"""

    _BLOCK_TAGS = frozenset({"p", "h1", "h2", "h3", "h4", "h5", "h6", "li"})
    _SKIP_TAGS = frozenset({"script", "style"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self._buffer: list[str] = []
        self._in_block = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
        elif tag in self._BLOCK_TAGS:
            self._flush()
            self._in_block = True

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in self._BLOCK_TAGS:
            self._flush()
            self._in_block = False

    def handle_data(self, data: str) -> None:
        if self._in_block and self._skip_depth == 0:
            self._buffer.append(data)

    def _flush(self) -> None:
        text = " ".join("".join(self._buffer).split())
        if text:
            self.lines.append(text)
        self._buffer = []

    def close(self) -> None:
        self._flush()
        super().close()


def extract_lines_from_html(html: str) -> list[str]:
    """HTML文書から段落・見出し単位のテキスト行を抽出する。

    Args:
        html: mtg-jp.com 総合ルールページのHTML全文。

    Returns:
        タグを除去した行のリスト（`parse_rules_lines` にそのまま渡せる形式）。
    """
    extractor = _ParagraphExtractor()
    extractor.feed(html)
    extractor.close()
    return extractor.lines
