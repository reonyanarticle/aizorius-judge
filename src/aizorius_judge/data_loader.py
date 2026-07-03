"""検索インデックスの構築とロード（ChromaDB＋BM25）。

パース済みCR（data/comprehensive_rules_{en,ja}.json）から日英併記コーパスを作り、
ChromaDB（cosine・永続化）と BM25 のインデックスを構築する。Embedding はローカルの
Sentence Transformers（multilingual-e5-base・接頭辞 query:/passage:）で計算し、
外部APIは使わない。再構築の要否はソースのSHA-256とモデル名を collection metadata に
記録して判定する（LLM不使用・決定論）。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import chromadb
import numpy as np
from numpy.typing import NDArray
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from aizorius_judge.models import CorpusEntry
from aizorius_judge.settings import Settings

logger = logging.getLogger(__name__)

__all__ = [
    "EmbeddingModel",
    "SearchIndex",
    "build_or_load_index",
    "load_corpus",
    "tokenize",
]

COLLECTION_NAME = "rules"

_TOKEN_RE = re.compile(r"\d{3}\.\d+[a-z]?|\d+[a-z]?|[a-zA-Z][a-zA-Z']*")
_CJK_RE = re.compile(r"[぀-ヿ㐀-鿿]+")


def tokenize(text: str) -> list[str]:
    """BM25用トークナイザ（形態素解析器に依存しない決定論的処理）。

    英数字は単語単位（ルール番号 "702.9b" は1トークンで保持）、日本語（かな・漢字）は
    文字バイグラムに分解する。日英併記テキストと日本語クエリの両方に同じ関数を使う。

    Args:
        text: 対象テキスト。

    Returns:
        トークンのリスト。
    """
    lowered = text.lower()
    tokens = _TOKEN_RE.findall(lowered)
    for chunk in _CJK_RE.findall(lowered):
        if len(chunk) == 1:
            tokens.append(chunk)
        else:
            tokens.extend(chunk[i : i + 2] for i in range(len(chunk) - 1))
    return tokens


def load_corpus(data_dir: Path) -> list[CorpusEntry]:
    """パース済みCRから日英併記コーパスを作る（英語が正文・番号で対応付け）。"""
    en_doc = json.loads(
        (data_dir / "comprehensive_rules_en.json").read_text(encoding="utf-8")
    )
    ja_doc = json.loads(
        (data_dir / "comprehensive_rules_ja.json").read_text(encoding="utf-8")
    )
    ja_texts = {rule["number"]: rule["text"] for rule in ja_doc["rules"]}
    return [
        CorpusEntry(
            number=rule["number"],
            text_en=rule["text"],
            text_ja=ja_texts.get(rule["number"]),
            section=rule["section"],
            category=rule["category"],
        )
        for rule in en_doc["rules"]
    ]


class EmbeddingModel:
    """E5系の接頭辞（query:/passage:）を扱うローカルEmbeddingのラッパ。

    デバイスは settings の指定（mps）を試し、失敗したら cpu にフォールバックする。
    """

    def __init__(self, model_name: str, device: str) -> None:
        self.model_name = model_name
        try:
            self._model = SentenceTransformer(model_name, device=device)
            self.device = device
        except Exception:
            logger.warning(
                "device=%s でのロードに失敗。cpu にフォールバックする", device
            )
            self._model = SentenceTransformer(model_name, device="cpu")
            self.device = "cpu"
        self._is_e5 = "e5" in model_name.lower()

    def encode_passages(self, texts: list[str]) -> NDArray[np.float32]:
        prefix = "passage: " if self._is_e5 else ""
        vectors = self._model.encode(
            [prefix + t for t in texts],
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)

    def encode_query(self, text: str) -> NDArray[np.float32]:
        prefix = "query: " if self._is_e5 else ""
        vectors = self._model.encode(
            [prefix + text], normalize_embeddings=True, show_progress_bar=False
        )
        return np.asarray(vectors, dtype=np.float32)[0]


class Reranker:
    """多言語 Cross-Encoder の薄いラッパ（bge-reranker-v2-m3。max_length制限でMPSのOOMを防ぐ）。"""

    def __init__(self, model_name: str, device: str) -> None:
        from sentence_transformers import CrossEncoder

        self.model_name = model_name
        self._model = CrossEncoder(model_name, device=device, max_length=512)

    def rank(self, query: str, passages: list[str]) -> list[int]:
        """passages をクエリ関連度の降順に並べたインデックス列を返す。"""
        scores = self._model.predict(
            [[query, p] for p in passages], batch_size=16, show_progress_bar=False
        )
        return list(np.argsort(-np.asarray(scores)))


@dataclass
class SearchIndex:
    """検索に必要なランタイム依存の束（lifespanで生成し、検索層へ注入する）。"""

    corpus: list[CorpusEntry]
    by_number: dict[str, CorpusEntry]
    collection: chromadb.Collection
    bm25: BM25Okapi
    embedder: EmbeddingModel
    reranker: Reranker | None


def _source_fingerprint(data_dir: Path, model_name: str) -> str:
    """再構築判定用の指紋（CR版のSHA-256＋モデル名。MANIFESTが版の正本）。"""
    manifest = json.loads((data_dir / "MANIFEST.json").read_text(encoding="utf-8"))
    hashes = "+".join(source["sha256"] for source in manifest["sources"].values())
    return f"{hashes}+{model_name}"


def build_or_load_index(settings: Settings) -> SearchIndex:
    """ChromaDBインデックスを構築（または既存を再利用）し、BM25とともに返す。

    collection metadata の指紋（CR版ハッシュ＋モデル名）が一致すれば再利用し、
    不一致なら削除して再構築する。BM25はコーパスから毎回構築する（数秒・非永続）。
    """
    corpus = load_corpus(settings.data_dir)
    embedder = EmbeddingModel(settings.embedding_model, settings.embedding_device)
    fingerprint = _source_fingerprint(settings.data_dir, embedder.model_name) + "+dual"

    client = chromadb.PersistentClient(path=str(settings.data_dir / "chromadb"))
    try:
        existing_collection = client.get_collection(COLLECTION_NAME)
    except Exception:  # NotFoundError（chromadbのバージョンで型が揺れるため広く受ける）
        existing_collection = None
    # 言語別ベクトル（en/ja 各1エントリ。番号は metadata の number で引く）
    expected_count = sum(2 if entry.text_ja else 1 for entry in corpus)
    is_fresh = (
        existing_collection is not None
        and (existing_collection.metadata or {}).get("fingerprint") == fingerprint
        and existing_collection.count() == expected_count
    )
    if is_fresh and existing_collection is not None:
        collection = existing_collection
        logger.info("既存インデックスを再利用: %d vectors", collection.count())
    else:
        logger.info("インデックスを再構築する（ベクトル数=%d）", expected_count)
        if existing_collection is not None:
            client.delete_collection(COLLECTION_NAME)
            # delete直後の同名createはハンドルが無効化されることがあるためクライアントを作り直す
            client = chromadb.PersistentClient(path=str(settings.data_dir / "chromadb"))
        collection = client.create_collection(
            COLLECTION_NAME,
            metadata={"hnsw:space": "cosine", "fingerprint": fingerprint},
        )
        ids: list[str] = []
        texts: list[str] = []
        metadatas: list[dict[str, str]] = []
        for entry in corpus:
            ids.append(f"{entry.number}#en")
            texts.append(f"{entry.number} {entry.text_en}")
            metadatas.append({"number": entry.number, "section": entry.section})
            if entry.text_ja:
                ids.append(f"{entry.number}#ja")
                texts.append(f"{entry.number} {entry.text_ja}")
                metadatas.append({"number": entry.number, "section": entry.section})
        embeddings = embedder.encode_passages(texts)
        batch = 500
        for start in range(0, len(ids), batch):
            collection.add(
                ids=ids[start : start + batch],
                embeddings=embeddings[start : start + batch],
                metadatas=metadatas[start : start + batch],  # type: ignore[arg-type]
            )
        logger.info("ChromaDB 構築完了: %d vectors", collection.count())

    reranker = (
        Reranker(settings.reranker_model, embedder.device)
        if settings.reranker_model
        else None
    )
    bm25 = BM25Okapi([tokenize(entry.embedding_text()) for entry in corpus])
    return SearchIndex(
        corpus=corpus,
        by_number={entry.number: entry for entry in corpus},
        collection=collection,
        bm25=bm25,
        embedder=embedder,
        reranker=reranker,
    )
