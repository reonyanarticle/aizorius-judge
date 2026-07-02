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
from aizorius_judge.rules_parser import extract_lines_from_html, parse_rules_lines

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
    return RulesDocument(
        language=language,
        effective_date=effective_date,
        source_sha256=_sha256(source_path),
        rules=rules,
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    manifest = json.loads(
        (REPO_ROOT / "data" / "MANIFEST.json").read_text(encoding="utf-8")
    )

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
        out_path = REPO_ROOT / "data" / f"comprehensive_rules_{language}.json"
        out_path.write_text(document.model_dump_json(indent=1), encoding="utf-8")
        logger.info(
            "%s: %d rules -> %s (effective %s)",
            language,
            len(document.rules),
            out_path.relative_to(REPO_ROOT),
            document.effective_date,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
