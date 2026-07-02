#!/usr/bin/env bash
# PostToolUse(Edit|Write) hook — 編集した .py ファイルだけ自動整形（Black＋Ruffのimport整列のみ）。
# 目的: 整形漏れ/lint 起因の手戻りを防ぐ（.claude/rules/python.md: 整形=Black, lint=Ruff）。
# 非ブロッキング（常に exit 0）。対象が .py でない/存在しない/uv 未導入なら素通し。
#
# 重要: 意味を変える autofix（F401 未使用import削除等）は行わない。編集は
# 「import追加→使用箇所追加」の順に複数回に分かれるため、中間状態で F401 を
# autofix すると追加直後の import が消えて NameError になる。
# hook が直すのは整形（Black）と import 並び（Ruff --select I）まで。
# それ以外の lint は /qa・stop-gate.sh・pre-commit・CI で検出する。

input=$(cat)

# stdin JSON から tool_input.file_path を取り出す（jq 非依存で python3 を使用）
file=$(printf '%s' "$input" | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin)
    print((d.get("tool_input") or {}).get("file_path",""))
except Exception:
    print("")' 2>/dev/null)

[ -z "$file" ] && exit 0
case "$file" in
  *.py) ;;
  *) exit 0 ;;
esac
[ -f "$file" ] || exit 0

cd "$CLAUDE_PROJECT_DIR" 2>/dev/null || exit 0
command -v uv >/dev/null 2>&1 || exit 0

uv run ruff check --fix --select I -q "$file" >/dev/null 2>&1
uv run black -q "$file"                       >/dev/null 2>&1
exit 0
