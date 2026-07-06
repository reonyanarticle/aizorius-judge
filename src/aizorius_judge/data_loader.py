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
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import chromadb
import numpy as np
from chromadb.api import ClientAPI
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
    "normalize_text",
    "tokenize",
]

COLLECTION_NAME = "rules"

_TOKEN_RE = re.compile(r"\d{3}\.\d+[a-z]?|\d+[a-z]?|[a-zA-Z][a-zA-Z']*")
_CJK_RE = re.compile(r"[぀-ヿ㐀-鿿]+")


def normalize_text(text: str) -> str:
    """照合用の正規化（NFKC＋小文字化）。

    日本語クエリの全角半角ゆれ（"７０２．９ｂ"・全角英字・全角スペース）を吸収する。
    BM25のトークン化と用語集照合の両方で同じ正規化を使う（片側だけだと照合が割れる）。
    """
    return unicodedata.normalize("NFKC", text).lower()


def _stem_en(token: str) -> str:
    """英語トークンの軽量ステミング（決定論・辞書不要）。

    BM25 は表層一致なので "triggers"/"triggered"/"triggering" が別トークンになり、
    英語クエリの再現率を下げる（hold-out 計測で表面化）。コーパス側とクエリ側に
    **同じ**変換を通すことで一致させる（変換結果が英単語である必要はない）。
    ルール番号など数字を含むトークンは対象外。
    """
    if any(ch.isdigit() for ch in token):
        return token
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith(("sses", "xes", "zes", "ches", "shes")) and len(token) > 4:
        # passes/boxes/matches 型の -es 複数形のみ。"ses" まで含めると phases/cases
        # （サイレントe＋s）が phas/cas に化けて単数形と不一致になる（レビュー指摘）
        return token[:-2]
    if token.endswith("s") and not token.endswith("ss") and len(token) > 3:
        return token[:-1]
    if token.endswith("ing") and len(token) > 5:
        return token[:-3]
    if token.endswith("ed") and len(token) > 4:
        return token[:-2]
    return token


def tokenize(text: str) -> list[str]:
    """BM25用トークナイザ（形態素解析器に依存しない決定論的処理）。

    英数字は単語単位（ルール番号 "702.9b" は1トークンで保持・英語は軽量ステミング）、
    日本語（かな・漢字）は文字バイグラムに分解する。日英併記テキストと日本語クエリの
    両方に同じ関数を使う。全角半角は NFKC で正規化してから切る（"７０２．９ｂ" も
    "702.9b" として拾う）。

    Args:
        text: 対象テキスト。

    Returns:
        トークンのリスト。
    """
    lowered = normalize_text(text)
    tokens = [_stem_en(token) for token in _TOKEN_RE.findall(lowered)]
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
    """多言語 Cross-Encoder の薄いラッパ（bge-reranker-v2-m3）。

    max_length / batch_size はマシン依存の設定（settings.py から注入 →
    `RERANKER_MAX_LENGTH` / `RERANKER_BATCH_SIZE`）。既定の 1024/8 は M4/MPS の実測:
    512では長いルールの日本語側が切られたまま採点されており、1024×batch8 で
    OOMなし・golden k7 0.905→0.909（must_cite）・MRR 0.785→0.792・p50 悪化なし（2026-07-06）。
    """

    def __init__(
        self, model_name: str, device: str, max_length: int = 1024, batch_size: int = 8
    ) -> None:
        from sentence_transformers import CrossEncoder

        self.model_name = model_name
        self._batch_size = batch_size
        self._model = CrossEncoder(model_name, device=device, max_length=max_length)

    def rank(self, query: str, passages: list[str]) -> list[int]:
        """passages をクエリ関連度の降順に並べたインデックス列を返す。"""
        scores = self._model.predict(
            [[query, p] for p in passages],
            batch_size=self._batch_size,
            show_progress_bar=False,
        )
        return list(np.argsort(-np.asarray(scores)))


@dataclass
class SearchIndex:
    """検索に必要なランタイム依存の束（lifespanで生成し、検索層へ注入する）。

    glossary_terms は「照合用語（小文字化済み）→ 参照ルール番号」の対応で、
    用語の長い順にソート済み（長い用語ほど特異的なので優先して照合する）。
    """

    corpus: list[CorpusEntry]
    by_number: dict[str, CorpusEntry]
    collection: chromadb.Collection
    bm25: BM25Okapi
    embedder: EmbeddingModel
    reranker: Reranker | None
    glossary_terms: list[tuple[str, list[str]]]
    glossary_section_terms: list[tuple[str, list[str]]]


# セクション参照を展開する章の大きさ上限（親ルール数）。大きな章（113誘発型能力等）を
# 汎用語から展開すると候補が洪水して全指標が悪化するため、小さな章（ステップ・スタック等）に限る
GLOSSARY_SECTION_MAX_PARENTS = 8
# 大きな章のセクション参照を「章の先頭K親」（定義・動作原理が並ぶ）に絞って展開する既定値。
# 全スキップ比で recall@7 0.746→0.752 / must_cite@7 0.895→0.905・劣化なし（2026-07-04 計測）
GLOSSARY_LARGE_SECTION_HEAD = 8


def load_glossary_terms(
    data_dir: Path, known_numbers: set[str], large_section_head: int = 0
) -> tuple[list[tuple[str, list[str]]], list[tuple[str, list[str]]]]:
    """glossary.json から照合用語→ルール番号の対応表を2系統作る。

    日本語用語・英語用語の両方を照合キーにする（英語は小文字化）。用語の長い順に並べる。

    Returns:
        (explicit_terms, section_terms):
        - explicit_terms: 定義文が個別番号で参照するルール（例 威迫→702.111）。融合で通常重み。
        - section_terms: セクション参照（例 アンタップ・ステップ→rule 502）を章の**親ルール**
          （レター無し番号）に展開したもの。小さな章（親 ≤ GLOSSARY_SECTION_MAX_PARENTS）に限る。
          汎用語で候補が洪水しないよう、融合では**弱い重みの補助系統**として使う（search.py）。
    """
    path = data_dir / "glossary.json"
    if not path.exists():
        logger.warning(
            "%s が無いため用語集系統は無効（scripts/parse_rules.py で生成）", path
        )
        return [], []
    parents_by_section: dict[str, list[str]] = {}
    for number in sorted(known_numbers):
        section, _, rest = number.partition(".")
        if rest and rest.isdigit():  # レター無し＝親ルール
            parents_by_section.setdefault(section, []).append(number)
    for parents in parents_by_section.values():
        # 文字列ソートだと "903.10" が "903.2" より前に来る。「章の先頭K親」を数値順で
        # 取れるよう数値ソートにする
        parents.sort(key=lambda n: int(n.partition(".")[2]))

    explicit_terms: list[tuple[str, list[str]]] = []
    section_terms: list[tuple[str, list[str]]] = []
    for entry in json.loads(path.read_text(encoding="utf-8")):
        rules = [n for n in entry["rules"] if n in known_numbers]
        section_rules: list[str] = []
        for section in entry.get("sections", []):
            parents = parents_by_section.get(section, [])
            if len(parents) > GLOSSARY_SECTION_MAX_PARENTS:
                # 大きな章は全展開すると候補が洪水する（実測）。large_section_head 指定時のみ
                # 章の**先頭K親**（章の定義・動作原理が並ぶ）に絞って展開する
                if large_section_head <= 0:
                    continue
                parents = parents[:large_section_head]
            section_rules += [n for n in parents if n not in rules]
        keys = []
        if entry.get("term_ja"):
            keys.append(normalize_text(entry["term_ja"]))
        if entry.get("term_en"):
            keys.append(normalize_text(entry["term_en"]))
        for key in keys:
            if rules:
                explicit_terms.append((key, rules))
            if section_rules:
                section_terms.append((key, section_rules))
    explicit_terms.sort(key=lambda pair: -len(pair[0]))
    section_terms.sort(key=lambda pair: -len(pair[0]))
    return explicit_terms, section_terms


def _source_fingerprint(data_dir: Path, model_name: str) -> str:
    """再構築判定用の指紋（CR版のSHA-256＋モデル名。MANIFESTが版の正本）。"""
    manifest = json.loads((data_dir / "MANIFEST.json").read_text(encoding="utf-8"))
    hashes = "+".join(source["sha256"] for source in manifest["sources"].values())
    return f"{hashes}+{model_name}"


def _get_existing_collection(client: ClientAPI) -> chromadb.Collection | None:
    """既存コレクションを取得する（無ければ None）。

    「無い」以外の例外（DB破損・権限等）は握りつぶさず伝播させる——黙って再構築に
    倒すと障害が見えなくなるため。NotFoundError の型は chromadb のバージョンで揺れる
    ので、まず例外の型名で判定し、メッセージの部分一致は「型名に notfound を含まない
    旧バージョンの ValueError 系」に限った最後の砦とする（契約はテストで固定）。
    """
    try:
        return client.get_collection(COLLECTION_NAME)
    except Exception as error:
        type_name = type(error).__name__.lower()
        if "notfound" in type_name:
            return None
        if type_name in ("valueerror", "invalidcollectionexception") and (
            "does not exist" in str(error)
        ):
            return None
        raise


def _is_reusable(
    collection: chromadb.Collection | None, fingerprint: str, expected_count: int
) -> bool:
    """既存コレクションを再利用できるか（指紋＝CR版＋モデルと件数の一致）。"""
    return (
        collection is not None
        and (collection.metadata or {}).get("fingerprint") == fingerprint
        and collection.count() == expected_count
    )


def _build_collection(
    data_dir: Path,
    corpus: list[CorpusEntry],
    embedder: EmbeddingModel,
    fingerprint: str,
    had_existing: bool,
) -> chromadb.Collection:
    """言語別ベクトル（number#en / number#ja）で ChromaDB コレクションを構築する。"""
    client = chromadb.PersistentClient(path=str(data_dir / "chromadb"))
    if had_existing:
        client.delete_collection(COLLECTION_NAME)
        # delete直後の同名createはハンドルが無効化されることがあるためクライアントを作り直す
        client = chromadb.PersistentClient(path=str(data_dir / "chromadb"))
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
    return collection


def build_or_load_index(settings: Settings) -> SearchIndex:
    """ChromaDBインデックスを構築（または既存を再利用）し、BM25とともに返す。

    collection metadata の指紋（CR版ハッシュ＋モデル名）が一致すれば再利用し、
    不一致なら削除して再構築する。BM25はコーパスから毎回構築する（数秒・非永続）。
    """
    corpus = load_corpus(settings.data_dir)
    embedder = EmbeddingModel(settings.embedding_model, settings.embedding_device)
    fingerprint = _source_fingerprint(settings.data_dir, embedder.model_name) + "+dual"

    client = chromadb.PersistentClient(path=str(settings.data_dir / "chromadb"))
    existing = _get_existing_collection(client)
    # 言語別ベクトル（en/ja 各1エントリ。番号は metadata の number で引く）
    expected_count = sum(2 if entry.text_ja else 1 for entry in corpus)
    if _is_reusable(existing, fingerprint, expected_count):
        collection = existing
        assert collection is not None  # _is_reusable が None を除外済み
        logger.info("既存インデックスを再利用: %d vectors", collection.count())
    else:
        logger.info("インデックスを再構築する（ベクトル数=%d）", expected_count)
        collection = _build_collection(
            settings.data_dir, corpus, embedder, fingerprint, existing is not None
        )

    reranker = (
        Reranker(
            settings.reranker_model,
            embedder.device,
            max_length=settings.reranker_max_length,
            batch_size=settings.reranker_batch_size,
        )
        if settings.reranker_model
        else None
    )
    bm25 = BM25Okapi([tokenize(entry.embedding_text()) for entry in corpus])
    known_numbers = {entry.number for entry in corpus}
    glossary_terms, glossary_section_terms = load_glossary_terms(
        settings.data_dir, known_numbers, large_section_head=GLOSSARY_LARGE_SECTION_HEAD
    )
    return SearchIndex(
        corpus=corpus,
        by_number={entry.number: entry for entry in corpus},
        collection=collection,
        bm25=bm25,
        embedder=embedder,
        reranker=reranker,
        glossary_terms=glossary_terms,
        glossary_section_terms=glossary_section_terms,
    )
