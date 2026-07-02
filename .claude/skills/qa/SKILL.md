---
name: qa
description: 品質ゲートを一括実行する。「QAして」「チェック回して」「品質ゲートを通して」で起動、または実装作業の仕上げに積極的に使う。Ruff(lint)→Black(--check)→basedpyright(型)→pytest(テスト)の順に実行し、失敗があれば修正して再実行、全部通るまで繰り返してから結果を表で報告する。
model: inherit
allowed-tools: Bash(uv run:*), Read, Edit, Grep, Glob
---

# /qa — 品質ゲート一括実行

`.claude/rules/python.md` のツールチェーンを一括で回す。CIに出す前・コミット前・実装の区切りで使う。
Stop フック（`.claude/hooks/stop-gate.sh`）が同等の検査を自動実行するが、本 skill は**修正まで含めて**完了させる。

## 手順（この順で。前段が失敗したら直してから次へ）
1. `uv run ruff check .` — lint。自動修正可能なものは `uv run ruff check --fix .`（意味を変える fix は差分を確認してから）。
2. `uv run black --check .` — 整形チェック。失敗したら `uv run black .` で整形。
3. `uv run basedpyright` — 型チェック。エラーは握りつぶさず（`# type: ignore` の安易な追加禁止）、型を直す。
4. `uv run pytest -q` — テスト。失敗したら原因を特定して修正（テストを弱める方向の修正は理由を明示）。

- コード未実装・ツール未導入の段階では、その項目を SKIP として報告する（エラーにしない）。
- 修正を入れたら**必ず全段を再実行**する（部分実行で緑と報告しない）。

## 出力
| 項目 | 結果 | 備考 |
|---|---|---|
| ruff / black / basedpyright / pytest | PASS / FAIL→修正→PASS / SKIP | 修正内容の1行要約 |

最後に「全て PASS」か「未解決の FAIL（理由と提案）」を明言する。
