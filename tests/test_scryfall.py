"""Scryfallクライアントの単体テスト（MockTransportで実APIを叩かない）と、
実カードでのライブテスト（既定で除外・`pytest -m live_scryfall` で明示実行）。
"""

from __future__ import annotations

import json

import httpx
import pytest

from aizorius_judge.errors import CardNotFoundError
from aizorius_judge.scryfall import USER_AGENT, ScryfallClient

BOLT = {
    "id": "abc-123",
    "name": "Lightning Bolt",
    "printed_name": "稲妻",
    "mana_cost": "{R}",
    "type_line": "Instant",
    "oracle_text": "Lightning Bolt deals 3 damage to any target.",
    "colors": ["R"],
    "color_identity": ["R"],
    "keywords": [],
}

RULINGS = {
    "data": [
        {
            "source": "wotc",
            "published_at": "2004-10-04",
            "comment": "The damage can be redirected to a planeswalker.",
        }
    ]
}


def make_client(handler) -> ScryfallClient:
    transport = httpx.MockTransport(handler)
    return ScryfallClient(httpx.AsyncClient(transport=transport))


async def test_lookup_card_fuzzy_and_user_agent() -> None:
    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        assert request.url.path == "/cards/named"
        assert request.url.params["fuzzy"] == "稲妻"
        return httpx.Response(200, json=BOLT)

    card = await make_client(handler).lookup_card("稲妻")
    assert card.name == "Lightning Bolt"
    assert card.printed_name == "稲妻"
    assert card.mana_cost == "{R}"
    assert seen_requests[0].headers["User-Agent"] == USER_AGENT


async def test_lookup_card_not_found_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"object": "error"})

    with pytest.raises(CardNotFoundError):
        await make_client(handler).lookup_card("zzz_not_a_card")


async def test_get_card_rulings() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/cards/named":
            return httpx.Response(200, json=BOLT)
        assert request.url.path == "/cards/abc-123/rulings"
        return httpx.Response(200, json=RULINGS)

    card, rulings = await make_client(handler).get_card_rulings("Lightning Bolt")
    assert card.name == "Lightning Bolt"
    assert len(rulings) == 1
    assert "planeswalker" in rulings[0].comment


async def test_rate_limit_interval() -> None:
    import time

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=BOLT)

    client = make_client(handler)
    started = time.monotonic()
    await client.lookup_card("a")
    await client.lookup_card("b")
    # 2リクエスト目は最低100msの間隔が空く
    assert time.monotonic() - started >= 0.1


@pytest.mark.live_scryfall
async def test_live_japanese_fuzzy_lookup() -> None:
    """実API: 日本語カード名のfuzzy解決（稲妻→Lightning Bolt）。"""
    async with httpx.AsyncClient() as http:
        card = await ScryfallClient(http).lookup_card("稲妻")
    assert card.name == "Lightning Bolt"


@pytest.mark.live_scryfall
async def test_live_rulings_orcish_bowmasters() -> None:
    """実API: 実戦頻出カード（オークの弓使い）の裁定取得。"""
    async with httpx.AsyncClient() as http:
        card, rulings = await ScryfallClient(http).get_card_rulings("オークの弓使い")
    assert card.name == "Orcish Bowmasters"
    assert rulings, "公式裁定が1件以上あるはず"
    print(
        json.dumps([r.model_dump() for r in rulings[:2]], ensure_ascii=False, indent=1)
    )
