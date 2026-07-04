"""Scryfall API クライアント（カード情報・公式裁定の取得）。

- `httpx.AsyncClient` を注入で受け取る（lifespanで生成・テストではMockTransport差し替え）。
- レート制限遵守: リクエスト間に最低 100ms の間隔、User-Agent 付与（.claude/rules/coding.md）。
- 日英カード名の fuzzy 検索に対応（`/cards/named?fuzzy=`）。該当なしは `CardNotFoundError`。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from aizorius_judge.errors import CardNotFoundError, ScryfallError
from aizorius_judge.models import Card, CardRuling

logger = logging.getLogger(__name__)

__all__ = ["USER_AGENT", "ScryfallClient"]

USER_AGENT = "aizorius-judge/0.1 (+https://github.com/reonyanarticle/aizorius-judge)"
BASE_URL = "https://api.scryfall.com"
MIN_INTERVAL_SECONDS = 0.1


class ScryfallClient:
    """Scryfall API の薄いクライアント（検索結果を返すだけ。要約・裁定生成はしない）。"""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http
        self._last_request_at = 0.0
        self._lock = asyncio.Lock()

    async def _get(
        self,
        path: str,
        params: dict[str, str] | None = None,
        not_found_means_card: bool = True,
    ) -> dict[str, Any]:
        """GETの共通処理（レート制限・エラー整形）。

        Args:
            path: APIパス。
            params: クエリパラメータ。
            not_found_means_card: 404を「カードが見つからない」と解釈するか。
                カード特定後の2段目（rulings等）の404はカード不在ではないため False。
        """
        async with self._lock:
            wait = MIN_INTERVAL_SECONDS - (time.monotonic() - self._last_request_at)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_at = time.monotonic()
        try:
            response = await self._http.get(
                f"{BASE_URL}{path}", params=params, headers={"User-Agent": USER_AGENT}
            )
        except httpx.HTTPError as error:
            raise ScryfallError(f"Scryfall request failed: {error}") from error
        if response.status_code == 404 and not_found_means_card:
            raise CardNotFoundError(params.get("fuzzy", path) if params else path)
        if response.status_code != 200:
            raise ScryfallError(f"Scryfall HTTP {response.status_code}: {path}")
        try:
            return response.json()
        except ValueError as error:
            raise ScryfallError(f"Scryfall invalid JSON: {path}") from error

    async def lookup_card(self, card_name: str) -> Card:
        """カード名（日英・多少の表記ゆれ可）からカード情報を引く。

        Raises:
            CardNotFoundError: fuzzy検索でも特定できない場合。
            ScryfallError: API呼び出しの失敗。
        """
        started = time.perf_counter()
        data = await self._get("/cards/named", params={"fuzzy": card_name})
        card = _to_card(data)
        logger.info(
            "lookup_card %r -> %s took_ms=%.0f",
            card_name,
            card.name,
            (time.perf_counter() - started) * 1000,
        )
        return card

    async def get_card_rulings(self, card_name: str) -> tuple[Card, list[CardRuling]]:
        """カードの公式裁定リストを取得する（カード特定→rulings_uri）。"""
        data = await self._get("/cards/named", params={"fuzzy": card_name})
        card = _to_card(data)
        rulings_data = await self._get(
            f"/cards/{data['id']}/rulings", not_found_means_card=False
        )
        rulings = [
            CardRuling(
                source=item.get("source", ""),
                published_at=item.get("published_at", ""),
                comment=item.get("comment", ""),
            )
            for item in rulings_data.get("data", [])
        ]
        logger.info("get_card_rulings %r -> %d件", card.name, len(rulings))
        return card, rulings


def _to_card(data: dict[str, Any]) -> Card:
    faces = data.get("card_faces") or []

    def face_fallback(key: str) -> Any:
        """トップレベルに無い属性を第1面から補う（Transform/MDFCはP/T等が各面にある）。"""
        value = data.get(key)
        if value is not None:
            return value
        return faces[0].get(key) if faces else None

    oracle_text = data.get("oracle_text") or "\n//\n".join(
        face.get("oracle_text", "") for face in faces
    )
    return Card(
        name=data.get("name", ""),
        printed_name=data.get("printed_name"),
        mana_cost=data.get("mana_cost")
        or "".join(face.get("mana_cost", "") for face in faces),
        type_line=data.get("type_line", ""),
        oracle_text=oracle_text,
        colors=data.get("colors") or [],
        color_identity=data.get("color_identity") or [],
        power=face_fallback("power"),
        toughness=face_fallback("toughness"),
        loyalty=face_fallback("loyalty"),
        keywords=data.get("keywords") or [],
    )
