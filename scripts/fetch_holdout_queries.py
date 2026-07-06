"""hold-out 口語クエリ集の取得（boardgames.stackexchange.com・MTGタグ）。

検索改善の汎化チェック用に、dataset とは独立した実ユーザーの質問文を取得する
（過学習検知の hold-out。経緯は docs/PLAN.md、判定基準は docs/ARCHITECTURE.md §5）。

- コンテンツは CC BY-SA 4.0。**リポジトリには含めない**（ローカル取得・gitignore。
  CR原文と同じ扱い）。帰属情報（投稿URL・著者名・著者プロフィールURL・ライセンス）を
  各レコードに保持する。
- 採点用の弱ラベルとして、採用回答（accepted answer）本文中の CRルール番号を
  正規表現で抽出する（LLM不使用・決定論）。
- Stack Exchange API の利用作法: 匿名クォータ内・gzip・リクエスト間 1s sleep・
  backoff フィールド遵守。

実行: uv run python scripts/fetch_holdout_queries.py [--pages 2]
出力: evaluation/holdout/se-questions.jsonl（1問=1行・コミット対象外）
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "evaluation" / "holdout"
API = "https://api.stackexchange.com/2.3"
SITE = "boardgames"
TAG = "magic-the-gathering"
USER_AGENT = "aizorius-judge/0.1 (+https://github.com/reonyanarticle/aizorius-judge)"
# withbody 相当の組み込みフィルタ（質問・回答の本文を含める）
FILTER = "withbody"

_RULE_NUMBER_RE = re.compile(r"\b(\d{3}\.\d+[a-z]?)\b")
_TAG_RE = re.compile(r"<[^>]+>")


def _get(client: httpx.Client, path: str, params: dict[str, Any]) -> dict[str, Any]:
    """API呼び出し（backoff遵守・エラーは例外）。"""
    response = client.get(f"{API}{path}", params={"site": SITE, **params})
    response.raise_for_status()
    payload = response.json()
    if backoff := payload.get("backoff"):
        logger.warning("API backoff %ss", backoff)
        time.sleep(float(backoff))
    time.sleep(1.0)  # 匿名クォータへの礼儀（スロットリング）
    return payload


def _strip(html_text: str) -> str:
    return html.unescape(_TAG_RE.sub(" ", html_text or ""))


def fetch_questions(
    client: httpx.Client, pages: int, sort: str = "votes"
) -> list[dict[str, Any]]:
    """採用回答つきの質問を取得する（得票順 or 新着順）。"""
    items: list[dict[str, Any]] = []
    for page in range(1, pages + 1):
        payload = _get(
            client,
            "/search/advanced",
            {
                "tagged": TAG,
                "accepted": "True",
                "sort": sort,
                "order": "desc",
                "pagesize": 100,
                "page": page,
                "filter": FILTER,
            },
        )
        items += payload.get("items", [])
        if not payload.get("has_more"):
            break
    return items


def fetch_answers(
    client: httpx.Client, answer_ids: list[int]
) -> dict[int, dict[str, Any]]:
    """採用回答の本文をID指定でまとめて取得する（100件ずつ）。"""
    answers: dict[int, dict[str, Any]] = {}
    for start in range(0, len(answer_ids), 100):
        chunk = answer_ids[start : start + 100]
        payload = _get(
            client,
            f"/answers/{';'.join(map(str, chunk))}",
            {"pagesize": 100, "filter": FILTER},
        )
        for item in payload.get("items", []):
            answers[int(item["answer_id"])] = item
    return answers


def main() -> int:
    """SEから採用回答つき質問を取得し、帰属・弱ラベルつきJSONLをローカルに書く。"""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages", type=int, default=2, help="100問/ページ")
    parser.add_argument(
        "--sort",
        choices=["votes", "creation"],
        default="votes",
        help="votes=定番問中心（古い投稿に偏る）/ creation=新しい投稿（改番ノイズが少ない）",
    )
    parser.add_argument("--out", default="se-questions.jsonl")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / args.out

    with httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=30.0, follow_redirects=True
    ) as client:
        questions = fetch_questions(client, args.pages, args.sort)
        accepted_ids = [
            int(q["accepted_answer_id"]) for q in questions if "accepted_answer_id" in q
        ]
        answers = fetch_answers(client, accepted_ids)

    records = []
    for question in questions:
        answer = answers.get(int(question.get("accepted_answer_id", -1)))
        if not answer:
            continue
        answer_text = _strip(str(answer.get("body", "")))
        cited = sorted(set(_RULE_NUMBER_RE.findall(answer_text)))
        owner = question.get("owner", {})
        records.append(
            {
                "question_id": question["question_id"],
                "creation_date": question.get(
                    "creation_date"
                ),  # UNIX秒（年代別分析用）
                "title": html.unescape(str(question.get("title", ""))),
                "body": _strip(str(question.get("body", "")))[:2000],
                "link": question.get("link"),
                "score": question.get("score"),
                "author": owner.get("display_name"),
                "author_link": owner.get("link"),
                "license": question.get("content_license", "CC BY-SA 4.0"),
                "answer_cited_rules": cited,
                "answer_score": answer.get("score"),
            }
        )

    with out_path.open("w", encoding="utf-8") as out:
        for record in records:
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
    with_rules = sum(1 for r in records if r["answer_cited_rules"])
    logger.info(
        "%d問取得（うち採用回答にCR番号引用あり %d問）-> %s",
        len(records),
        with_rules,
        out_path.relative_to(REPO_ROOT),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
