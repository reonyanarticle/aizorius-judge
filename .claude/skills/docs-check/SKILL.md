---
name: docs-check
description: AIzorius Judgeのdocs/規約を機械的に点検する。「docsチェック」「ドキュメント規約を確認」「docsの整合を見て」で起動。ファイル名(全大文字・フラット・アンダースコア禁止)、ASCII直書き図の不在(図はmermaid)、内部リンクの実在、正本の一意性(決定の二重記載なし)、を検査してPASS/FAILで報告する。
model: sonnet
allowed-tools: Bash(ls:*), Bash(find:*), Bash(grep:*), Read, Glob, Grep
---

# /docs-check — docs 規約リンター（AIzorius Judge 固有）

`.claude/rules/documentation.md` の規約を機械的に検査する。手作業の grep を毎回組み立てる代わりに、
この skill で一括点検する。

## 検査項目
1. **命名・配置**：`docs/` 直下はフラット（サブディレクトリ禁止）。ファイル名は**全て大文字**、区切りは
   ハイフンのみ（アンダースコア禁止）。例外は `README.md` のみ。
   - `find docs -mindepth 2 -type f` でサブディレクトリ内ファイルを検出（0件が正）。
   - `ls docs` を読み、小文字・アンダースコアを含む名（`README.md` 除く）を挙げる。
2. **図は mermaid**：ASCII/罫線の直書き図が無いこと。
   - `grep -rnP '[─━│┃┌┐└┘├┤┬┴┼╔╗╚╝═║]' docs/` が mermaid ブロック外でヒットしないか確認し、
     ヒット行は目視で図かどうか判別する。
   - **矢印（→ ↔ 等）と `|` は検査対象にしない**：矢印は本文の参照表記で正当に使われ、`|` は markdown
     テーブルで必ずヒットするため、含めると誤検知過多で検査が形骸化する。
   - 例外：`README.md`（ルート）のアーキテクチャ要点のコードブロック図は既知の許容（1分説明のための簡易図）。
3. **内部リンクの実在**：doc 内の相対リンク（`[..](FILE.md)` / `[..](docs/FILE.md)`）先が実在するか。
   リンクを抽出し、リンク元ファイルのディレクトリ基準で対象ファイルの有無を確認する（リンク切れは FAIL）。
   `.claude/rules/documentation.md` 内の**リンク記法の例示**は対象外。
4. **正本の一意性（軽チェック）**：docs 間で同じ決定が二重記載されていないか、目視で疑わしい箇所を挙げる
   （重複しそうなら片方を正本にし、もう片方はリンクのみにする規約）。
5. **フェーズ番号の閉じ込め**：フェーズ番号（Phase 0/1/1.5…）が `docs/PLAN.md` 以外に無いこと。
   - `grep -rnE "Phase [0-9]" README.md CLAUDE.md docs/ .claude/rules .claude/skills .claude/agents src/ scripts/ tests/ evaluation/ | grep -v docs/PLAN.md` が0件（ファイル名も対象。MTG用語の "Combat Phase" 等の英語カテゴリ名は除外してよい）。

## 出力
各項目を PASS / FAIL（＋該当ファイル・行）で表にまとめ、FAIL には最小の修正案を1行添える。
規約の正本は `.claude/rules/documentation.md`。判断が割れる箇所は「要目視」と明示する（自動判定を過信しない）。
