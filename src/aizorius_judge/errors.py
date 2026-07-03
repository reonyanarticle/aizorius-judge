"""独自例外の階層。

呼び出し側（ツール層）が対処できる粒度で送出する。MCPツールの「該当なし」は
例外を握って分かりやすいメッセージに整形する（.claude/rules/coding.md）。
"""

from __future__ import annotations

__all__ = ["AizoriusJudgeError", "CardNotFoundError", "ScryfallError"]


class AizoriusJudgeError(Exception):
    """AIzorius Judge のルート例外。"""


class ScryfallError(AizoriusJudgeError):
    """Scryfall API の呼び出し失敗（HTTPエラー・タイムアウト等）。"""


class CardNotFoundError(ScryfallError):
    """カード名が（fuzzy検索でも）特定できなかった。

    Attributes:
        card_name: 検索したカード名。
    """

    def __init__(self, card_name: str) -> None:
        super().__init__(f"card not found: {card_name}")
        self.card_name = card_name
