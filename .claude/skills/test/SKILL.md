---
name: test
description: テスト・検査を実行して結果を報告するだけの軽量スキル（修正はしない）。「テスト回して」「テスト通る？」「チェックだけして」で起動。Ruff・Black・basedpyright・pytestをチェックモードで実行しPASS/FAILの表を返す。失敗の修正が必要なら /qa を使う。
model: haiku
allowed-tools: Bash(uv run:*), Read
---

# /test — テスト実行と報告（実行専用・修正なし）

品質ゲートを**実行して結果を報告するだけ**の軽量スキル。修正はしない（修正込みは `/qa`）。
安価なモデルで足りる作業のため haiku で動かす。

## 手順（全部実行してから報告。途中で止めない）
1. `uv run ruff check .`
2. `uv run black --check .`
3. `uv run basedpyright`
4. `uv run pytest -q`

## 出力
| 項目 | 結果 | 失敗数・要点（1行） |
|---|---|---|

- FAIL があれば失敗メッセージの**要点だけ**（ファイル:行・エラー種別）を抜粋する。全文を貼らない。
- 修正はせず、「修正が必要なら /qa を実行」と添えて終了する。
