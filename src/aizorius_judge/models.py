"""型定義の集約。

Pydanticモデル・dataclass・Enum は原則ここに置く（.claude/rules/python.md §0）。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

__all__ = [
    "CorpusEntry",
    "DatasetQuestion",
    "EvaluationCriteria",
    "ExpectedAnswer",
    "RuleEntry",
    "RulesDocument",
    "SearchResult",
]


class CorpusEntry(BaseModel):
    """検索コーパスの1ルール（日英併記。インデックス構築と検索結果の元データ）。

    Attributes:
        number: ルール番号（例 "702.9b"）。コーパス内で一意。
        text_en: 英語本文（正文）。
        text_ja: 日本語本文（和訳。対応する番号が無い場合は None）。
        section: 大区分の番号（例 "702"）。
        category: 章タイトル（例 "Keyword Abilities"）。
    """

    number: str
    text_en: str
    text_ja: str | None = None
    section: str
    category: str

    def embedding_text(self) -> str:
        """Embedding・BM25 に投入する日英併記テキスト（bake-off と同形式）。"""
        base = f"{self.number} {self.text_en}"
        return f"{base}\n{self.text_ja}" if self.text_ja else base


class SearchResult(BaseModel):
    """検索結果の1件（スコア付きルール）。"""

    number: str
    text_en: str
    text_ja: str | None = None
    section: str
    category: str
    score: float


class RuleEntry(BaseModel):
    """総合ルール（CR）の1ルール（またはサブルール）。

    Attributes:
        number: ルール番号（例 "702.9b", "100.1"）。
        text: ルール本文。
        section: 大区分の番号（例 "702"）。
        category: 章タイトル（例 "Keyword Abilities"）。
    """

    number: str = Field(min_length=1)
    text: str = Field(min_length=1)
    section: str = Field(min_length=1)
    category: str


class ExpectedAnswer(BaseModel):
    """評価データセット1問の期待回答（docs/EVALUATION.md §3）。"""

    conclusion: str = Field(min_length=1)
    rules_cited: list[str] = Field(min_length=1)
    key_facts: list[str] = Field(min_length=1)


class EvaluationCriteria(BaseModel):
    """評価データセット1問の採点基準。"""

    must_cite_rules: list[str] = Field(min_length=1)
    forbidden_mistakes: list[str] = Field(min_length=1)


class DatasetQuestion(BaseModel):
    """評価データセット（evaluation/dataset.json）の1問。

    Attributes:
        id: 一意ID（例 "commander-007"）。
        category: docs/EVALUATION.md §3 のカテゴリ。
        question: ルール質問（日本語）。
        expected_tools: 期待されるツール呼び出し。
        expected_answer: 期待回答（結論・引用ルール・重要事実）。
        retrieval_relevant_rules: 検索が返すべきルール番号の完全集合（recall@kの正解）。
        evaluation_criteria: 採点基準。
        source: 照合したCRの版（例 "CR 2026-06-19 (en)"）。
        notes: 網羅性への注記・保留事項。
    """

    id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    question: str = Field(min_length=1)
    expected_tools: list[str] = Field(min_length=1)
    expected_answer: ExpectedAnswer
    retrieval_relevant_rules: list[str] = Field(min_length=1)
    evaluation_criteria: EvaluationCriteria
    source: str = Field(min_length=1)
    notes: str | None = None


class RulesDocument(BaseModel):
    """パース済みCR全体。版情報つき（data/comprehensive_rules*.json のスキーマ）。

    Attributes:
        language: "en" | "ja"。
        effective_date: CRの発効日（ISO 8601）。
        source_sha256: パース元ファイルの SHA-256（版固定。data/MANIFEST.json と対応）。
        rules: ルールの配列。
    """

    language: str
    effective_date: str
    source_sha256: str
    rules: list[RuleEntry]
