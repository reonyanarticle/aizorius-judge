"""CR原文（英語TXT・日本語HTML）をパースして data/comprehensive_rules_{en,ja}.json を生成する。

版情報（発効日・SHA-256）は data/MANIFEST.json を正本として引き継ぐ。
実行: uv run python scripts/parse_rules.py
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from pathlib import Path

from aizorius_judge.models import RulesDocument
from aizorius_judge.rules_parser import (
    extract_lines_from_html,
    merge_glossaries,
    parse_glossary_en,
    parse_glossary_ja,
    parse_rules_lines,
)

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_document(
    language: str, source_path: Path, effective_date: str
) -> RulesDocument:
    """CR原文ファイル1つを `RulesDocument` に変換する。

    Args:
        language: "en" | "ja"。
        source_path: 原文ファイル（en=TXT / ja=HTML）。
        effective_date: CRの発効日（MANIFEST由来）。

    Returns:
        パース済みの `RulesDocument`。
    """
    raw = source_path.read_text(encoding="utf-8-sig")
    lines = (
        extract_lines_from_html(raw)
        if source_path.suffix == ".html"
        else raw.splitlines()
    )
    rules = parse_rules_lines(lines)
    # 原文側の重複（mtg-jp HTML に 505.4 が2回ある等）を初出優先でユニーク化する
    seen: set[str] = set()
    unique_rules = []
    for rule in rules:
        if rule.number in seen:
            logger.warning("%s: 番号 %s が重複（初出を採用）", language, rule.number)
            continue
        seen.add(rule.number)
        unique_rules.append(rule)
    return RulesDocument(
        language=language,
        effective_date=effective_date,
        source_sha256=_sha256(source_path),
        rules=unique_rules,
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    manifest = json.loads(
        (REPO_ROOT / "data" / "MANIFEST.json").read_text(encoding="utf-8")
    )

    documents = {}
    for key, language in (("cr_en", "en"), ("cr_ja", "ja")):
        source = manifest["sources"][key]
        source_path = REPO_ROOT / source["local_file"]
        if not source_path.exists():
            logger.error(
                "%s が無い。先に scripts/fetch_rules.sh を実行する。", source_path
            )
            return 1
        if _sha256(source_path) != source["sha256"]:
            logger.error(
                "%s のSHA-256がMANIFESTと不一致（版が変わった可能性）。", source_path
            )
            return 1
        document = build_document(language, source_path, source["effective_date"])
        documents[language] = document
        out_path = REPO_ROOT / "data" / f"comprehensive_rules_{language}.json"
        out_path.write_text(document.model_dump_json(indent=1), encoding="utf-8")
        logger.info(
            "%s: %d rules -> %s (effective %s)",
            language,
            len(document.rules),
            out_path.relative_to(REPO_ROOT),
            document.effective_date,
        )

    # パース結果の自己検証: 抽出が静かに壊れた（サイト構造変更等）場合にここで止める。
    # 閾値は現行版の実測（en 3153 / ja 3123 / 共通率 ~99%）に安全側の余裕を持たせた値。
    en_numbers = {rule.number for rule in documents["en"].rules}
    ja_numbers = {rule.number for rule in documents["ja"].rules}
    if len(en_numbers) < 3000 or len(ja_numbers) < 3000:
        logger.error(
            "ルール数が異常に少ない（en=%d ja=%d）。抽出の破損を疑う。",
            len(en_numbers),
            len(ja_numbers),
        )
        return 1
    coverage = len(en_numbers & ja_numbers) / len(ja_numbers)
    if coverage < 0.97:
        logger.error(
            "日英の番号一致率が低い（%.3f）。版ズレまたは抽出の破損を疑う。", coverage
        )
        return 1
    logger.info(
        "自己検証OK: en=%d ja=%d 共通=%d（ja側一致率 %.3f）",
        len(en_numbers),
        len(ja_numbers),
        len(en_numbers & ja_numbers),
        coverage,
    )

    # 用語集（日英マージ）: 用語→ルール番号の決定論的対応表として検索の第3系統に使う
    en_raw = (REPO_ROOT / manifest["sources"]["cr_en"]["local_file"]).read_text(
        encoding="utf-8-sig"
    )
    ja_raw = (REPO_ROOT / manifest["sources"]["cr_ja"]["local_file"]).read_text(
        encoding="utf-8-sig"
    )
    glossary = merge_glossaries(parse_glossary_en(en_raw), parse_glossary_ja(ja_raw))
    glossary_path = REPO_ROOT / "data" / "glossary.json"
    glossary_path.write_text(
        json.dumps(
            [entry.model_dump() for entry in glossary], ensure_ascii=False, indent=1
        ),
        encoding="utf-8",
    )
    with_ja = sum(1 for entry in glossary if entry.term_ja)
    with_rules = sum(1 for entry in glossary if entry.rules)
    logger.info(
        "glossary: %d terms (ja対応 %d / ルール参照あり %d) -> %s",
        len(glossary),
        with_ja,
        with_rules,
        glossary_path.relative_to(REPO_ROOT),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
