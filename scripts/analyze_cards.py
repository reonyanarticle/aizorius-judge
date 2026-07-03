"""Scryfallを用いた実カード分析（MCP層の前倒し検証）。

実在カードで次を検証し、レポートを書く:
1. 日英カード名の fuzzy 解決と公式裁定の取得（lookup_card / get_card_rulings 経路）
2. カードの keywords（Scryfall付与）が用語集経由で正しいCRルールに対応するか
   （クライアントが「カード情報→ルール検索」と連携する動線の検証）
3. カードを主語にした日本語質問で search_rules が関連ルールを返すか

実行: uv run python scripts/analyze_cards.py（実APIを叩く。レート制限は client が遵守）
出力: evaluation/reports/card-analysis.md
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import httpx

from aizorius_judge.data_loader import build_or_load_index
from aizorius_judge.scryfall import ScryfallClient
from aizorius_judge.search import HybridSearcher
from aizorius_judge.settings import Settings

REPO_ROOT = Path(__file__).resolve().parent.parent

# (問い合わせ名, カードを主語にした質問)
CARDS: list[tuple[str, str]] = [
    ("稲妻", "稲妻はプレインズウォーカーを対象にできますか"),
    ("オークの弓使い", "相手がドローしたときに誘発する能力はスタックに載りますか"),
    ("孤独", "想起でクリーチャーを唱えたときの生け贄はいつ発生しますか"),
    (
        "敏捷なこそ泥、ラガバン",
        "疾駆で唱えたクリーチャーはターン終了時にどうなりますか",
    ),
    ("波使い", "エレメンタルのトークンは召喚酔いの影響を受けますか"),
]


async def main() -> int:
    logging.basicConfig(level=logging.WARNING)
    settings = Settings()
    settings.reranker_model = None  # 分析はマッピング検証が目的なので高速構成
    index = build_or_load_index(settings)
    searcher = HybridSearcher(index)
    glossary_by_en = {
        term: rules
        for term, rules in index.glossary_terms
        if term and term[0].isascii()
    }

    lines: list[str] = [
        "# 実カード分析（Scryfall連携・MCP層の前倒し検証）",
        "",
        "実在カードで「カード特定→キーワード→CRルール」の動線を検証した結果。",
        "",
    ]
    async with httpx.AsyncClient(timeout=15) as http:
        client = ScryfallClient(http)
        for query_name, question in CARDS:
            card, rulings = await client.get_card_rulings(query_name)
            keyword_rows = []
            for keyword in card.keywords:
                rules = glossary_by_en.get(keyword.lower())
                keyword_rows.append(
                    f"{keyword}→{','.join(rules) if rules else '対応なし'}"
                )
            groups = searcher.search(question, max_groups=3)
            lines += [
                f"## {card.printed_name or card.name}（{card.name}）",
                f"- fuzzy解決: `{query_name}` → {card.name} ✓ / 公式裁定 {len(rulings)}件",
                f"- keywords→ルール対応: {', '.join(keyword_rows) if keyword_rows else '（キーワードなし）'}",
                f"- 質問「{question}」→ 検索: "
                + ", ".join(f"{g.parent_number}（{g.category}）" for g in groups),
                "",
            ]

    out = REPO_ROOT / "evaluation" / "reports" / "card-analysis.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"report -> {out.relative_to(REPO_ROOT)}")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
