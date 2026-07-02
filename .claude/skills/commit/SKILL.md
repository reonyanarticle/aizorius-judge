---
name: commit
description: 変更をステージしてConventional Commits形式（日本語）でコミットする。「コミットして」「commitして」「これをコミット」で起動。コミット前に鍵・ChromaDB永続化データ・巨大生成物の混入と品質ゲート（/qa相当）を確認し、pushは明示要求がない限りしない。
model: sonnet
allowed-tools: Bash(git status:*), Bash(git diff:*), Bash(git add:*), Bash(git commit:*), Bash(git log:*), Bash(git branch:*), Bash(uv run:*), Read, Grep
---

# /commit — 安全な日本語コミット

AIzorius Judge のコミット反復を標準化する。**機微データ・生成物の混入防止と品質ゲート通過を優先**する。

## 手順
1. `git status` と `git diff`（ステージ済み・未ステージ両方）で変更内容を把握する。何を含めるかユーザーの
   意図が曖昧なら、ステージ対象を確認してから進む。
2. **混入チェック（必須）**。ステージ差分に次が無いか確認する。疑わしければ**コミットを止めて警告**する。
   - APIキー・シークレット（`.env` 実体、`GPT4_API_KEY` の値等）
   - `data/chromadb/` の永続化データ（.gitignore 対象。誤って force add されていないか）
   - 巨大な生成物（パース済みCR JSONの差分が意図したものか、モデルのキャッシュ等）
   - 依存への `anthropic` / `openai` の混入（`pyproject.toml` の diff。eval optional のみ許可 → `.claude/rules/coding.md`）
3. **品質ゲート**：`.py` に変更がある場合、`uv run ruff check .` / `uv run black --check .` /
   `uv run basedpyright` / `uv run pytest -q` を通す（コードが未実装の段階ではスキップ）。
   失敗したらコミットせず、失敗内容を報告して修正を先に行う。
4. **コミットメッセージ**は `type(scope): 日本語の要約`。
   - type 例：`feat` / `fix` / `docs` / `test` / `refactor` / `chore`。scope 例：`server` / `search` / `tools` / `data` / `eval` / `docs` / `claude`。
   - 要約は簡潔に「何を・なぜ」。必要なら本文に箇条書きで理由（what ではなく why）。
5. コミット末尾に次のフッターを付ける（モデル名を固定しない）：

   ```
   Co-Authored-By: Claude <noreply@anthropic.com>
   ```
6. **push はしない**（明示的に頼まれたときだけ）。現在ブランチが `main` なら、コミット前に作業ブランチを切る
   ことを提案する（デフォルトブランチへの直コミットを避ける）。

## 出力
コミット後、`git log -1 --stat` の要約を1〜3行で報告する。混入疑い・品質ゲート失敗で止めた場合は理由と対処を示す。
