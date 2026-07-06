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

from aizorius_judge.models import GlossaryEntry, RuleEntry

__all__ = [
    "extract_lines_from_html",
    "merge_glossaries",
    "parse_glossary_en",
    "parse_glossary_ja",
    "parse_rules_lines",
]

_SECTION_RE = re.compile(r"^(\d{3})\.\s+(.+)$")
_RULE_RE = re.compile(r"^(\d{3})\.(\d+[a-z]?)\.?\s+(.+)$")
_GLOSSARY_TITLES = ("Glossary", "用語集")
# 個別ルール参照。CRの定義文は "rule 702.9b" のほか "rules 509.1b–c"（複数形＋レター範囲）
# や "rules 613.2, 707.2, and 707.3"（列挙）を多用するため、"rule" 直後だけでなく
# 番号トークン全般を拾う（###.# 形式は定義文中でルール参照以外に現れない。
# 実在しない番号は data_loader.load_glossary_terms が known_numbers で除外する）。
# 範囲終端は「単独の英字1文字」に限る（(?![a-z])）——"rule 702.19b - keyword ability" の
# ような地の文のハイフンを b〜k のレンジと誤解して実在番号を汚染しないため
_RULE_REF_RE = re.compile(r"(\d{3}\.\d+)([a-z])?(?:\s*[–—-]\s*([a-z])(?![a-z]))?")
# 個別ルール（"510.2"）は除外しつつ、文末ピリオド（"rules 510."）は受け付ける
_SECTION_REF_RE = re.compile(r"rules? (\d{3})(?!\.\d|\d)")
_JA_GLOSS_H5_RE = re.compile(r"<h5><a id=\"g_[^\"]*\">(.*?)</a></h5>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_READING_RE = re.compile(r"（[ぁ-ゖー・、\s]+）")


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

    # div/br もブロック境界として扱う——サイト構造の変更で <div> 直下や <br> 区切りに
    # 変わった場合に複数ルールが1行にマージされて丸ごと未パースになるのを防ぐ
    _BLOCK_TAGS = frozenset({"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "div"})
    _SELF_CLOSING_BREAKS = frozenset({"br"})
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
        elif tag in self._SELF_CLOSING_BREAKS:
            self._flush()
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


def _referenced_rules(text: str) -> tuple[list[str], list[str]]:
    """定義文中のルール参照を抽出する。

    Returns:
        (個別ルール番号のリスト（"702.111" 等）, セクション番号のリスト（"502" 等）)。
        レター範囲（"509.1b–c"）は各サブルールに展開する。セクション参照
        （例「See rule 502, "Untap Step."」）は検索側で親ルール群に展開する。
    """
    rules: dict[str, None] = {}
    for base, letter, range_end in _RULE_REF_RE.findall(text):
        if not letter:
            rules.setdefault(base, None)
            continue
        end = range_end if range_end and range_end >= letter else letter
        for code in range(ord(letter), ord(end) + 1):
            if (
                chr(code) in "lo"
            ):  # CRはサブルールのレターに l/o を使わない（1/0との混同回避）
                continue
            rules.setdefault(f"{base}{chr(code)}", None)
    sections: dict[str, None] = {}
    for number in _SECTION_REF_RE.findall(text):
        sections.setdefault(number, None)
    return list(rules), list(sections)


def parse_glossary_en(raw_text: str) -> list[GlossaryEntry]:
    """英語CR（TXT）の用語集をパースする。

    用語集の構造: 本文側（2度目）の "Glossary" 行から "Credits" 行まで、
    空行区切りのブロックが並び、各ブロックは「用語行＋定義行（複数可）」。
    """
    lines = raw_text.splitlines()
    glossary_positions = [
        i for i, line in enumerate(lines) if line.strip() == "Glossary"
    ]
    credits_positions = [i for i, line in enumerate(lines) if line.strip() == "Credits"]
    if len(glossary_positions) < 2 or len(credits_positions) < 2:
        return []
    region = lines[glossary_positions[1] + 1 : credits_positions[1]]

    entries: list[GlossaryEntry] = []
    block: list[str] = []
    for raw_line in [*region, ""]:
        line = raw_line.strip()
        if line:
            block.append(line)
            continue
        if len(block) >= 2:
            definition = " ".join(block[1:])
            rules, sections = _referenced_rules(definition)
            entries.append(
                GlossaryEntry(
                    term_en=block[0],
                    definition_en=definition,
                    rules=rules,
                    sections=sections,
                )
            )
        block = []
    return entries


def parse_glossary_ja(html: str) -> list[GlossaryEntry]:
    """日本語CR（HTML）の用語集をパースする。

    構造: `<h5><a id="g_...">威迫（いはく）／Menace</a></h5>` の見出しに続いて
    定義テキスト（インラインリンク含む）が次の h5 まで続く。
    用語は「日本語（読み）／English」形式で、English 部分が日英マージのキーになる。
    """
    matches = list(_JA_GLOSS_H5_RE.finditer(html))
    entries: list[GlossaryEntry] = []
    for index, match in enumerate(matches):
        term_raw = _TAG_RE.sub("", match.group(1)).strip()
        body_end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else match.end() + 4000
        )
        body_html = html[match.end() : body_end]
        # 用語集セクションの終端（divの閉じ等）で切る
        for terminator in ("</div>", "<h4>"):
            cut = body_html.find(terminator)
            if cut != -1:
                body_html = body_html[:cut]
        definition = " ".join(_TAG_RE.sub(" ", body_html).split())
        if "／" in term_raw:
            term_ja, _, term_en = term_raw.rpartition("／")
        else:
            term_ja, term_en = term_raw, term_raw
        term_ja = _READING_RE.sub("", term_ja).strip()
        rules, sections = _referenced_rules(definition)
        entries.append(
            GlossaryEntry(
                term_en=term_en.strip(),
                term_ja=term_ja or None,
                definition_ja=definition or None,
                rules=rules,
                sections=sections,
            )
        )
    return entries


def merge_glossaries(
    en_entries: list[GlossaryEntry], ja_entries: list[GlossaryEntry]
) -> list[GlossaryEntry]:
    """英語用語集を正とし、日本語用語集を英語用語キーで突き合わせて統合する。

    日本語側にしかない項目もそのまま残す（日本語クエリの用語照合に使うため）。
    """
    merged: dict[str, GlossaryEntry] = {}
    for entry in en_entries:
        merged[entry.term_en.lower()] = entry.model_copy()
    for ja_entry in ja_entries:
        key = ja_entry.term_en.lower()
        if key in merged:
            base = merged[key]
            base.term_ja = ja_entry.term_ja
            base.definition_ja = ja_entry.definition_ja
            for number in ja_entry.rules:
                if number not in base.rules:
                    base.rules.append(number)
            for section in ja_entry.sections:
                if section not in base.sections:
                    base.sections.append(section)
        else:
            merged[key] = ja_entry.model_copy()
    return list(merged.values())
