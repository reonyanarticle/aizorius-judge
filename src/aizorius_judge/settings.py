"""グローバル設定の集約（pydantic-settings）。

env / .env / デフォルトを型付きで統合する（.claude/rules/python.md §0）。
APIキーは不要（Scryfallは認証不要、Embeddingはローカル実行）。
ランタイム依存（Searcher・httpxクライアント等）はここに置かず、lifespanで生成して注入する。
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Settings"]


class Settings(BaseSettings):
    """AIzorius Judge の設定。すべて環境変数で上書き可能（未設定でも動く）。"""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    embedding_model: str = "intfloat/multilingual-e5-base"
    embedding_device: str = "mps"
    reranker_model: str | None = "BAAI/bge-reranker-v2-m3"
    # リランカー入力の上限とバッチはマシン依存（メモリとのトレードオフ）。既定は
    # M4/32GB での実測値（1024/8 で OOMなし・must_cite改善）。非力な環境では
    # RERANKER_MAX_LENGTH=512 / RERANKER_BATCH_SIZE=4 等に下げる
    reranker_max_length: int = 1024
    reranker_batch_size: int = 8
    data_dir: Path = Path("data")
